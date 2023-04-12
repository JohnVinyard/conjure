import * as THREE from "three";
import { OrbitControls } from "https://unpkg.com/three@0.139.2/examples/jsm/controls/OrbitControls.js";
import { select } from "d3-select";
import { scaleLinear } from "d3-scale";
import { axisBottom, axisLeft } from "d3-axis";
import { line } from "d3-shape";

const audioCache = {};
const context = new (window.AudioContext || window.webkitAudioContext)();

const fetchAudio = (url, context) => {
  const cached = audioCache[url];
  if (cached !== undefined) {
    return cached;
  }
  const audioBufferPromise = fetch(url).then(async (resp) => {
    const buffer = await resp.arrayBuffer();
    return context.decodeAudioData(buffer);
  });
  audioCache[url] = audioBufferPromise;
  return audioBufferPromise;
};

const playAudio = (url, context, start, duration) => {
  fetchAudio(url, context).then((audioBuffer) => {
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    source.start(0, start, duration);
  });
};

const visit = (typedArray, shape, visitor, scene) => {
  const stride = strides(shape);

  for (let i = 0; i < typedArray.length; i++) {
    const location = computeIndices(i, shape, stride);
    visitor(typedArray.at(i), location, scene);
  }
};

const dtypeToConstructor = (dtype) => {
  if (dtype === "<f4") {
    return Float32Array;
  }

  throw new Error("Not Implemented");
};

const product = (arr) => {
  if (arr.length === 0) {
    return 1;
  }
  return arr.reduce((accum, current) => accum * current, 1);
};

const strides = (shape) => {
  return shape.map((x, index, arr) => product(arr.slice(index + 1)));
};

const computeIndices = (flatIndex, shape, stride) => {
  return shape.map((sh, index) => {
    return Math.floor(flatIndex / stride[index]) % sh;
  });
};

const setupScene = (myCanvas) => {
  const axes = new THREE.AxesHelper();

  const scene = new THREE.Scene();
  scene.add(axes);

  const camera = new THREE.PerspectiveCamera(
    50,
    myCanvas.offsetWidth / myCanvas.offsetHeight
  );
  camera.position.set(10, 10, 10);
  camera.lookAt(scene.position);

  const renderer = new THREE.WebGLRenderer({ canvas: myCanvas });
  renderer.setClearColor(0xffffff, 1.0);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(myCanvas.offsetWidth, myCanvas.offsetHeight);

  const orbitControls = new OrbitControls(camera, renderer.domElement);
  orbitControls.maxPolarAngle = Math.PI * 0.5;
  orbitControls.minDistance = 0.1;
  orbitControls.maxDistance = 100;

  renderer.setAnimationLoop(() => {
    orbitControls.update();
    renderer.render(scene, camera);
  });

  return scene;
};

class TensorData {
  constructor(data, shape) {
    this.data = data;
    this.shape = shape;
    this.strides = strides(shape);
  }

  get totalSize() {
    return this.data.length;
  }

  get maxValue() {
    let max = 0;

    for (let i = 0; i < this.totalSize; i++) {
      const v = this.data.at(i);
      if (v > max) {
        max = v;
      }
    }

    return max;
  }

  get minValue() {
    let min = Infinity;

    for (let i = 0; i < this.totalSize; i++) {
      const v = this.data.at(i);
      if (v < min) {
        min = v;
      }
    }

    return min;
  }

  getChannelData(channel) {
    const [channelStride, elementStride] = this.strides;
    const output = [];

    const start = channel * channelStride;
    const channelSize = this.shape[1];
    const end = start + channelSize;

    for (let i = start; i < end; i += elementStride) {
      output.push(this.data.at(i));
    }
    return output;
  }

  indices(flat) {
    return computeIndices(flat, this.shape, this.strides);
  }

  visit(visitor, scene) {
    visit(this.data, this.shape, visitor, scene);
  }

  static async fromNpy(raw) {
    const headerAndData = raw.slice(8);
    const headerLen = new Uint16Array(headerAndData.slice(0, 2)).at(0);
    const arr = new Uint8Array(headerAndData.slice(2, 2 + headerLen));
    const str = String.fromCharCode(...arr);
    const dtypePattern = /('descr':\s+)'([^']+)'/;
    const shapePattern = /('shape':\s+)(\([^/)]+\))/;
    const dtype = str.match(dtypePattern)[2];
    const rawShape = str.match(shapePattern)[2];
    const hasTrailingComma = rawShape.slice(-2)[0] === ",";
    const truncated = rawShape.slice(1, hasTrailingComma ? -2 : -1);
    const massagedShape = `[${truncated}]`;
    const shape = JSON.parse(massagedShape);
    const arrayData = new (dtypeToConstructor(dtype))(
      headerAndData.slice(2 + headerLen)
    );
    return new TensorData(arrayData, shape);
  }

  static async fromURL(url) {
    return fetch(url).then(async (resp) => {
      const raw = await resp.arrayBuffer();
      return TensorData.fromNpy(raw);
    });
  }
}

class AudioView {
  constructor(elementId, tensor, url) {
    this.elementId = elementId;
    this.tensor = tensor;
    this.url = url;
    this.clickHandler = () => {
      playAudio(url, context, 0);
    };
  }

  static async renderURL(url, elementId) {
    const rawData = await fetchAudio(url, context);
    const channelData = rawData.getChannelData(0);
    const data = new TensorData(channelData, [channelData.length]);
    const view = new AudioView(elementId, data, url);
    view.render();
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  render() {
    const scene = setupScene(this.element);
    this.tensor.visit(renderAudioVisitor, scene);
    this.element.removeEventListener("click", this.clickHandler);
    this.element.addEventListener("click", this.clickHandler);
  }
}

const AUDIO_STEP = 512;

const renderAudioVisitor = (value, location, scene) => {
  const [x, y, z] = location;

  if (x % AUDIO_STEP !== 0) {
    return;
  }

  const size = 0.1;

  const color = new THREE.Color(0.5, 0.5, 0.5);

  const geometry = new THREE.BoxGeometry(size, Math.abs(value) * 50, size);
  const material = new THREE.MeshBasicMaterial({
    color,
  });
  const cube = new THREE.Mesh(geometry, material);
  scene.add(cube);
  cube.position.x = (x / AUDIO_STEP) * size;
  cube.position.y = 0;
  cube.position.z = 0;
};

const renderCubeVisitor = (value, location, scene) => {
  const [x, y, z] = location;

  const size = 0.5;

  const color = new THREE.Color(1 * value, 0.5 * value, 0.1 * value);

  const geometry = new THREE.BoxGeometry(size, size, size);
  const material = new THREE.MeshBasicMaterial({
    color,
  });
  const cube = new THREE.Mesh(geometry, material);
  scene.add(cube);
  cube.position.x = (x || 0) * size;
  cube.position.y = (y || 0) * size;
  cube.position.z = (z || 0) * size;
};

class TensorView {
  constructor(elementId, tensor) {
    this.elementId = elementId;
    this.tensor = tensor;
  }

  static async renderURL(url, elementId) {
    const data = await TensorData.fromURL(url);
    const view = new TensorView(elementId, data);
    view.render();
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  render() {
    const scene = setupScene(this.element);
    this.tensor.visit(renderCubeVisitor, scene);
  }
}

class SeriesView {
  constructor(elementId, tensor) {
    this.elementId = elementId;
    this.tensor = tensor;
  }

  static async renderURL(url, elementId) {
    const data = await TensorData.fromURL(url);
    const view = new SeriesView(elementId, data);
    view.render();
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  render() {
    const [nChannels, size] = this.tensor.shape;

    // TODO: get these values from the element
    const width = 500;
    const height = 500;

    this.element.innerHTML = "";

    const svg = select(`#${this.elementId}`)
      .append("svg")
      .attr("width", width)
      .attr("height", height)
      .append("g")
      .attr("transform", `translate(50, -10)`);

    // Add X axis
    const x = scaleLinear().domain([0, size]).range([0, width]);

    svg
      .append("g")
      .attr("transform", `translate(0, ${height})`)
      .call(axisBottom(x));

    // Add Y axis
    const y = scaleLinear().domain([0, 1]).range([0, height]);

    svg.append("g").call(axisLeft(y));

    const colors = ["#afa", "#faa"];

    // render lines for each "channel"
    for (let i = 0; i < nChannels; i++) {
      const data = this.tensor
        .getChannelData(i)
        .map((value, index) => ({ value, index }));

      svg
        .append("path")
        .datum(data)
        .attr("fill", "none")
        .attr("stroke", colors[i])
        .attr("stroke-width", 1.5)
        .attr(
          "d",
          line()
            .x((d) => x(d.index))
            .y((d) => y(d.value))
        );
    }
  }
}

const attachDataList = (parentId, data, itemElementName, transform) => {
  const parentElement = document.getElementById(parentId);
  parentElement.innerHTML = "";
  data.forEach((item) => {
    const child = document.createElement(itemElementName);
    const mutated = transform(item, child);
    parentElement.appendChild(mutated);
  });
};

const conjure = async ({
  element = null,
  metaData = null,
  style = { width: 500, height: 500 },
  refreshRate = null,
  feedOffset = null,
} = {}) => {
  if (element === null) {
    await Promise.allSettled(
      Array.from(document.querySelectorAll("[data-conjure]")).map((element) =>
        conjure({ element, style, refreshRate, feedOffset })
      )
    );
    return;
  }

  console.log(`Conjuring with feed offset ${feedOffset}`);

  const { key, public_uri, content_type, feed_uri } =
    metaData === null
      ? JSON.parse(element.getAttribute("data-conjure"))
      : metaData;

  const contentTypeToRenderClass = {
    "application/tensor+octet-stream": TensorView,
    "application/time-series+octet-stream": SeriesView,
    "audio/wav": AudioView,
  };

  const contentTypeToRootElementType = {
    "application/tensor+octet-stream": "canvas",
    "application/time-series+octet-stream": "div",
    "audio/wav": "canvas",
  };

  const renderer = contentTypeToRenderClass[content_type];
  const rootElement = contentTypeToRootElementType[content_type];

  const root = element;
  root.innerHTML = "";

  const container = document.createElement(rootElement);
  container.style = style;
  container.id = `display-${key}`;
  root.appendChild(container);

  await renderer.renderURL(public_uri, container.id);

  // TODO: If there's a refresh rate specified, periodically
  // check the feed.  If there's an item with a timestamp larger
  // than the one we've got, call conjure again with the same
  // refresh rate and the new highest offset

  if (refreshRate !== null && feed_uri) {
    const interval = setInterval(async () => {
      const searchParams = new URLSearchParams();

      if (feedOffset) {
        searchParams.append("offset", feedOffset);
      }

      const feed = await fetch(`${feed_uri}?${searchParams}`).then((resp) =>
        resp.json()
      );
      const onlyNew = feed.filter((item) => item.timestamp !== feedOffset);
      console.log(`Checked feed and found ${onlyNew.length} new items`);
      if (onlyNew.length) {
        clearInterval(interval);
        await conjure({
          element,
          metaData,
          refreshRate,
          feedOffset: onlyNew.slice(-1)[0].timestamp,
        });
      }
    }, refreshRate);
  }
};

document.addEventListener(
  "DOMContentLoaded",
  async () => {
    // TODO: Only do this if we're on the dashboard

    // TODO: Display the latest items from each function's feed,
    // all at once

    // list the functions
    const data = await fetch("/functions").then((resp) => resp.json());

    attachDataList("functions", data, "li", (d, c) => {
      c.innerText = `${d.name} - ${d.content_type}`;

      const preElement = document.createElement("pre");
      preElement.innerText = d.code;
      c.appendChild(preElement);

      c.addEventListener("click", async () => {
        // first, clear the display
        const display = document.getElementById("display");
        display.innerHTML = "";

        // TODO: Get the most recent key from the feed, only display
        // that key, and set it to auto-refresh

        // when a function is clicked, list its keys
        const { keys } = await fetch(d.url).then((resp) => resp.json());

        // create elements for each of the keys
        attachDataList("keys", keys, "div", (key, div) => {
          div.id = `id-${key}`;
          div.setAttribute(
            "data-conjure",
            JSON.stringify({
              key,
              feed_uri: `/feed/${d.id}`,
              public_uri: `/functions/${d.id}/${key}`,
              content_type: d.content_type,
            })
          );
          return div;
        });

        // hydrate all the conjure elements
        await conjure({ refreshRate: 5000 });

      });
      return c;
    });
  },
  false
);
