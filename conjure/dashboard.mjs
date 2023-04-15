import * as THREE from "https://unpkg.com/three@0.139.2/build/three.module.js";
import { OrbitControls } from "https://unpkg.com/three@0.139.2/examples/jsm/controls/OrbitControls.js";
import { select } from "https://cdn.jsdelivr.net/npm/d3-selection@3/+esm";
import { scaleLinear } from "https://cdn.jsdelivr.net/npm/d3-scale@3/+esm";
import {
  axisBottom,
  axisLeft,
} from "https://cdn.jsdelivr.net/npm/d3-axis@3/+esm";
import { line } from "https://cdn.jsdelivr.net/npm/d3-shape@3/+esm";

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

const playAudio = (url, context, start, duration, onComplete) => {
  fetchAudio(url, context).then((audioBuffer) => {
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    source.start(0, start, duration);
    setTimeout(onComplete, (duration || audioBuffer.duration) * 1000);
  });
};

const visit = (typedArray, shape, visitor, scene) => {
  const stride = strides(shape);

  const shapes = [];

  for (let i = 0; i < typedArray.length; i++) {
    const location = computeIndices(i, shape, stride);
    const shpe = visitor(typedArray.at(i), location, scene);
    shapes.push(shpe);
  }

  return shapes;
};

const dtypeToConstructor = (dtype) => {
  if (dtype === "<f4") {
    return Float32Array;
  }

  if (dtype === "<f8") {
    return Float64Array;
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

class World {
  constructor(myCanvas, cameraPosition) {
    const axes = new THREE.AxesHelper();

    const scene = new THREE.Scene();
    scene.add(axes);

    const camera = new THREE.PerspectiveCamera(
      50,
      myCanvas.offsetWidth / myCanvas.offsetHeight
    );
    camera.position.set(...cameraPosition);
    camera.lookAt(scene.position);

    const renderer = new THREE.WebGLRenderer({ canvas: myCanvas });
    renderer.setClearColor(0x000, 1.0);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(myCanvas.offsetWidth, myCanvas.offsetHeight);

    const orbitControls = new OrbitControls(camera, renderer.domElement);
    orbitControls.maxPolarAngle = Math.PI * 0.5;
    orbitControls.minDistance = 0.1;
    orbitControls.maxDistance = 100;

    const clock = new THREE.Clock(true);

    const light = new THREE.HemisphereLight(0xffffbb, 0x080820, 1);
    scene.add(light);

    this.scene = scene;
    this.renderer = renderer;
    this.clock = clock;
    this.camera = camera;
    this.orbitControls = orbitControls;

    this.elapsedTime = 0;

    this.sceneUpdater = null;
  }

  getObjectByName(name) {
    return this.scene.getObjectByName(name);
  }

  traverseChildren(func) {
    this.scene.children.forEach(func);
  }

  start() {
    this.renderer.setAnimationLoop(() => {
      this.elapsedTime += this.clock.getDelta();

      if (this.sceneUpdater !== null) {
        this.sceneUpdater(this.elapsedTime);
      }
      // TODO: I need to be able to inject code here, and get
      // the elapsed time passed in as a parameter
      this.orbitControls.update();
      this.renderer.render(this.scene, this.camera);
    });
  }

  stop() {
    throw new Error("Not Implemented");
  }
}

class TensorData {
  /**
   *
   * @param {TypedArray} data - flat, typed array
   * @param {Array} shape  - the shape of the multidimensional array
   * @param {Object} metadata - arbitrary key-value pairs for additional info
   */
  constructor(data, shape, metadata) {
    this.data = data;
    this.shape = shape;
    this.strides = strides(shape);
    this.metadata = metadata;
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
    return visit(this.data, this.shape, visitor, scene);
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
  constructor(elementId, tensor, url, stepSize = 512) {
    this.elementId = elementId;
    this.tensor = tensor;
    this.url = url;
    this.playStartTime = null;
    this.world = null;
    this.stepSize = stepSize;

    this.clickHandler = () => {
      this.playStartTime = this.world.elapsedTime;

      playAudio(url, context, 0, undefined, () => {
        // the audio is done playing;
        this.playStartTime = null;
      });
    };
  }

  static async renderURL(url, elementId) {
    const rawData = await fetchAudio(url, context);
    const samplerate = rawData.sampleRate;
    const channelData = rawData.getChannelData(0);
    const data = new TensorData(channelData, [channelData.length], {
      samplerate,
    });
    const view = new AudioView(elementId, data, url);
    view.render();
  }

  buildVisitor() {
    const renderAudioVisitor = (value, location, scene) => {
      const [x, y, z] = location;

      if (x % this.stepSize !== 0) {
        return;
      }

      const size = 0.1;

      const color = new THREE.Color(0x666666);

      const geometry = new THREE.BoxGeometry(size, Math.abs(value) * 50, size);
      const material = new THREE.MeshLambertMaterial({
        color,
      });
      const cube = new THREE.Mesh(geometry, material);

      cube.position.x = (x / this.stepSize) * size;
      cube.position.y = 0;
      cube.position.z = 0;

      cube.name = `${Math.floor(x / this.stepSize)}`;

      scene.add(cube);

      return cube;
    };

    return renderAudioVisitor;
  }

  get samplerate() {
    return this.tensor.metadata.samplerate;
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  render() {
    console.log(
      `Setting up scene with ${AudioView.name} and ${this.element.id}`
    );

    // set up the world and store a reference
    const world = new World(this.element, [50, 0, 50]);
    this.world = world;

    const visitor = this.buildVisitor();

    // render the initial scene
    this.tensor.visit(visitor, world.scene);

    // set the update function on the world
    world.sceneUpdater = (elapsedTime) => {
      if (this.playStartTime === null) {
        // the audio isn't currently playing, so there's
        // no need to animate anything
        return;
      }

      const currentTime = elapsedTime - this.playStartTime;
      const currentBlock = Math.round((currentTime * this.samplerate) / this.stepSize);
      // const cube = this.world.getObjectByName(currentBlock);

      this.world.traverseChildren((child) => {
        if (!child.material) {
          return;
        }

        if (child.name !== currentBlock.toString()) {
          child.scale.set(1, 1, 1);
          child.material.color.setHex(0x666666);
        } else {
          child.scale.set(2, 1, 1);
          child.material.color.setHex(0x999999);
        }
      });
    };

    world.start();

    this.element.removeEventListener("click", this.clickHandler);
    this.element.addEventListener("click", this.clickHandler);
  }
}

const renderCubeVisitor = (value, location, scene) => {
  const [x, y, z] = location;

  const size = 0.5;

  const color = new THREE.Color(1 * value, 0.5 * value, 0.1 * value);

  const geometry = new THREE.BoxGeometry(size, size, size);
  const material = new THREE.MeshBasicMaterial({
    color,
  });
  const cube = new THREE.Mesh(geometry, material);
  cube.position.x = (x || 0) * size;
  cube.position.y = (y || 0) * size;
  cube.position.z = (z || 0) * size;

  scene.add(cube);

  return cube;
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
    console.log(
      `Setting up scene with ${TensorView.name} and ${this.element.id}`
    );
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
    console.log(
      `Setting up scene with ${SeriesView.name} and ${this.element.id}`
    );
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

const conjure = async (
  {
    element = null,
    metaData = null,
    style = { width: "500px", height: "500px" },
    refreshRate = null,
    feedOffset = null,
  } = {
    style: { width: "500px", height: "500px" },
  }
) => {
  if (element === null) {
    const elements = document.querySelectorAll("[data-conjure]");
    for (let i = 0; i < elements.length; i++) {
      const el = elements[i];
      await conjure({ element: el, refreshRate, feedOffset });
    }
    return;
  }

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

  console.log(
    `conjuring with content-type: ${content_type}, class: ${renderer.name}, root element: ${rootElement.name}`
  );

  const root = element;
  root.innerHTML = "";

  const container = document.createElement(rootElement);
  container.style.width = style.width;
  container.style.height = style.height;
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
    // TODO: This is dumb.  This entire script should be separate,
    // or even generated server-side
    if (!window.location.href.includes("dashboard")) {
      conjure();
      return;
    }

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
        await conjure();
      });
      return c;
    });
  },
  false
);
