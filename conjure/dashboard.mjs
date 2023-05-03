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

const fetchJSON = async (url) => {
  const resp = await fetch(url);
  return resp.json();
};

const fetchText = async (url) => {
  const resp = await fetch(url);
  return resp.text();
};

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

  if (dtype === "<u4") {
    return Uint32Array;
  }

  throw new Error(`Type ${dtype} not implemented`);
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

    const light = new THREE.PointLight(0xffffff, 1, 100);
    light.position.set(1, 1, 1);
    scene.add(light);

    this.scene = scene;
    this.renderer = renderer;
    this.clock = clock;
    this.camera = camera;
    this.orbitControls = orbitControls;

    this.elapsedTime = 0;

    this.sceneUpdater = null;
  }

  get nChilidren() {
    return this.scene.children.length;
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

  get nDim() {
    return this.shape.length;
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

  toRGBA() {
    const arr = new Uint8ClampedArray(this.totalSize * 4);

    this.visit((value, loc, scene) => {
      const [x, y] = loc;
      const scaled = Math.floor(value * 255);
      const pos =
        Math.floor(x * this.strides[0]) + Math.floor(y * this.strides[1]);
      arr[pos] = scaled;
      arr[pos + 1] = scaled;
      arr[pos + 2] = scaled;
      arr[pos + 3] = scaled;
    });

    return arr;
  }

  getElement(channel) {
    // return a new tensor resulting from index
    // the first dimension of this one, or, if the
    // tensor is one dimensional, return the value
    if (this.nDim === 1) {
      return this.data.at(channel);
    }

    const channelStride = this.strides[0];

    const remainingShape = this.shape.slice(1);
    const start = channel * channelStride;
    const nElements = product(remainingShape);
    const newData = this.data.slice(start, start + nElements);
    return new TensorData(newData, remainingShape);
  }

  getChannelData(channel) {
    // TODO: replace this with the more general getElement
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

class TextView {
  constructor(elementId, tensor) {
    this.elementId = elementId;
    this.tensor = tensor;
  }

  static async renderURL(url, elementId) {
    const text = await fetchText(url);
    const view = new TextView(elementId, text);
    view.render();
  }

  render() {
    micro(`#${this.elementId}`, "text", this.tensor);
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
      const currentBlock = Math.round(
        (currentTime * this.samplerate) / this.stepSize
      );
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

class TensorMovieView {
  constructor(elementId, tensor, samplerate = 42) {
    this.elementId = elementId;
    this.tensor = tensor;
    this.world = null;
    this.samplerate = samplerate;

    this.playStartTime = null;

    const durationMs = (this.tensor.shape[0] / this.samplerate) * 1000;

    this.clickHandler = () => {
      this.playStartTime = this.world.elapsedTime;
      setTimeout(() => {
        this.playStartTime = null;
      }, durationMs);
    };

    this.textureCache = {};
  }

  textureAtPosition(index) {
    if (this.textureCache[index]) {
      return this.textureCache[index];
    }

    const textureData = this.tensor.getElement(index);

    // const intArray = new Uint8ClampedArray(textureData.data.buffer);
    const intArray = textureData.toRGBA();

    const width = textureData.shape[0];
    const height = textureData.shape[1];

    const texture = new THREE.DataTexture(
      intArray,
      width,
      height,
      THREE.RedFormat,
      THREE.UnsignedByteType
    );

    texture.needsUpdate = true;
    this.textureCache[texture];
    return texture;
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  static async renderURL(url, elementId) {
    const data = await TensorData.fromURL(url);
    const view = new TensorMovieView(elementId, data);
    view.render();
  }

  initScene() {
    const texture = this.textureAtPosition(0);
    const size = 0.5;

    // const color = new THREE.Color(1, 1, 1);

    const geometry = new THREE.PlaneBufferGeometry(size, size);

    const material = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      displacementMap: texture,
    });
    const cube = new THREE.Mesh(geometry, material);
    cube.name = "plane";
    cube.position.x = 0;
    cube.position.y = 0;
    cube.position.z = 0;

    this.world.scene.add(cube);
  }

  render() {
    // set up the world and store a reference
    const world = new World(this.element, [1, 0, 1]);
    this.world = world;

    // render the initial scene
    this.initScene();

    world.sceneUpdater = (elapsedTime) => {
      if (!this.playStartTime) {
        return;
      }

      const currentTime = elapsedTime - this.playStartTime;
      const currentFrame = Math.round(currentTime * this.samplerate);

      const texture = this.textureAtPosition(currentFrame);

      const plane = this.world.getObjectByName("plane");

      plane.material.bumpMap = texture;
      plane.material.needsUpdate = true;
    };

    this.element.removeEventListener("click", this.clickHandler);
    this.element.addEventListener("click", this.clickHandler);

    world.start();
  }
}

class TensorView {
  constructor(elementId, tensor) {
    this.elementId = elementId;
    this.tensor = tensor;
    this.world = null;
  }

  static async renderURL(url, elementId) {
    const data = await TensorData.fromURL(url);
    const view = new TensorView(elementId, data);
    view.render();
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  buildVisitor() {
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
    return renderCubeVisitor;
  }

  render() {
    console.log(
      `Setting up scene with ${TensorView.name} and ${this.element.id}`
    );

    // set up the world and store a reference
    const world = new World(this.element, [50, 0, 50]);
    this.world = world;

    const visitor = this.buildVisitor();

    // render the initial scene
    this.tensor.visit(visitor, world.scene);

    world.start();
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

// https://stackoverflow.com/questions/30003353/can-es6-template-literals-be-substituted-at-runtime-or-reused
const inject = (str, obj) => {
  return str.replace(/\${([^}{]+?)}/g, (x, g) => {
    if (g === "this") {
      return obj;
    }

    let value = obj[g];
    if (typeof value === "function") {
      value = value(obj);
    }

    return value;
  });
};

const micro = (
  rootElementSelector,
  templateId,
  data,
  mutate,
  hooks = null,
  baseRoot = null
) => {
  const normalizedHooks = hooks || {};

  const isSelector = typeof rootElementSelector === "string";

  const root = isSelector
    ? document.querySelector(rootElementSelector)
    : rootElementSelector;
  root.innerHTML = "";

  const normalizedBaseRoot = baseRoot || root;

  const template = document.getElementById(templateId);

  const normalized = Array.isArray(data) ? data : [data];

  const hook = normalizedHooks[templateId];

  normalized.forEach((d) => {
    const clone = template.content.firstElementChild.cloneNode(true);
    let mutated = null;

    // render any sub-templates
    const subTemplates = clone.querySelectorAll("[data-template]");
    subTemplates.forEach((template) => {
      micro(
        template,
        template.getAttribute("data-template"),
        data[template.getAttribute("data-source")],
        undefined,
        normalizedHooks,
        normalizedBaseRoot
      );
    });

    if (mutate) {
      mutated = mutate(clone, d);
    } else {
      clone.innerHTML = inject(clone.innerHTML, d);
    }

    const normalizedElement = mutated || clone;

    root.appendChild(normalizedElement);

    if (hook) {
      reactWhenAddedToDOM(normalizedBaseRoot, normalizedElement, d, hook);
      // hook(normalizedElement, d);
    }
  });
};

const changeView = async (
  path,
  fetchData,
  rootElementSelector,
  render,
  postRender = () => {}
) => {
  const pushPath = typeof path === "string" ? path : path.pathname;
  window.history.pushState({}, "", pushPath);
  const data = await fetchData(pushPath);
  render(rootElementSelector, data);
  postRender();
};

class URLPath {
  constructor() {}

  /**
   *
   * @param {URL} url
   */
  static fromURL(url) {
    throw new Error("Not Implemented");
  }

  get relativeUrl() {
    throw new Error("Not Implemented");
  }
}

class HomeURLPath extends URLPath {
  constructor() {
    super();
  }

  /**
   *
   * @param {URL} url
   */
  static fromURL(url) {
    const path = typeof url === "string" ? url : url.pathname;
    const segments = path.split("/").filter((segment) => segment.length);
    if (segments.length === 1 && segments[0] === "dashboard") {
      return new HomeURLPath();
    }
  }

  get relativeUrl() {
    return "/dashboard";
  }
}

class FunctioDetailUrlPath extends URLPath {
  constructor(functionId) {
    super();
    this.functionId = functionId;
  }

  /**
   *
   * @param {URL} url
   */
  static fromURL(url) {
    const path = typeof url === "string" ? url : url.pathname;
    const segments = path.split("/").filter((segment) => segment.length);
    if (
      segments.length === 3 &&
      segments[0] === "dashboard" &&
      segments[1] === "functions"
    ) {
      return new FunctioDetailUrlPath(segments[2]);
    }
  }

  get relativeUrl() {
    return `/dashboard/functions/${this.functionId}`;
  }
}

/**
 * NOTE: This is not a dashboard URL, but an API URL
 */
class FunctionIndexUrlPath extends URLPath {
  constructor(functionId, indexName, query) {
    super();
    this.functionId = functionId;
    this.indexName = indexName;
    this.query = query;
  }

  /**
   *
   * @param {URL} url
   */
  static fromURL(url) {
    const path = typeof url === "string" ? url : url.pathname;
    const segments = path.split("/").filter((segment) => segment.length);
    // [functions, id, indexes, name]
    if (
      segments.length === 4 &&
      segments[0] === "functions" &&
      segments[2] === "indexes"
    ) {
      // TODO: extract query string
      return new FunctionIndexUrlPath(segments[1], segments[3], "");
    }
  }

  get relativeUrl() {
    return `/functions/${this.functionId}/indexes/${this.indexName}?q=${this.query}`;
  }
}

class View {
  constructor(urlClass, templateId) {
    this._urlClass = urlClass;
    this._templateId = templateId;
  }

  get templateId() {
    return this._templateId;
  }

  get urlClass() {
    return this._urlClass;
  }

  async fetchData(url) {
    throw new Error("Not Implemented");
  }

  mutate(data) {
    return data;
  }

  render(rootElementSelector, data) {
    micro(rootElementSelector, this.templateId, this.mutate(data));
  }

  postRender() {
    throw new Error("Not Implemented");
  }
}

const debounce = (func, time) => {
  let handle = null;

  return (...args) => {
    if (handle) {
      clearTimeout(handle);
    }

    handle = setTimeout(async () => {
      await func(...args);
    }, time);
  };
};

const reactWhenAddedToDOM = (rootElementSelector, el, data, hook) => {
  if (el.isConnected) {
    hook(el, data);
    return;
  }

  const unique = Math.round(Math.random() * 1e7).toString(16);
  el.setAttribute("data-unique", unique);

  const observer = new MutationObserver((mutations, observer) => {
    for (let mutation of mutations) {
      for (let addedNode of mutation.addedNodes) {
        // find the corresponding connected node
        const connected = addedNode.querySelector(`[data-unique="${unique}"]`);
        observer.disconnect();
        hook(connected, data);
        return;
      }
    }
  });

  const rootElement =
    typeof rootElementSelector === "string"
      ? document.querySelector(rootElementSelector)
      : rootElementSelector;

  observer.observe(rootElement, {
    childList: true,
    subtree: false,
  });
};

class FunctionDetailView extends View {
  constructor() {
    super(FunctioDetailUrlPath, "function-detail");
  }

  async fetchData(url) {
    const instance = this.urlClass.fromURL(url);
    return fetchJSON(`/functions/${instance.functionId}`);
  }

  render(rootElementSelector, data) {
    micro(rootElementSelector, this.templateId, data, null, {
      "function-detail-index": (el, { name: indexName, description }) => {
        const input = el.querySelector("input");
        const searchResultsContainer = el.querySelector(".search-results");
        const totalResults = el.querySelector('.total-results');

        input.addEventListener(
          "input",
          debounce(async (event) => {
            const functionIndexUrl = new FunctionIndexUrlPath(
              data.id,
              indexName,
              event.target.value
            );

            const searchResults = await fetchJSON(functionIndexUrl.relativeUrl);

            totalResults.innerText = searchResults.length.toString();
            
            micro(
              searchResultsContainer,
              "index-search-result",
              searchResults,
              (srEl, sr) => {
                srEl.querySelector(".search-result-key").innerText = sr.key;
                const summary = srEl.querySelector(".search-result-summary");
                summary.innerText = JSON.stringify(sr, null, 4);
                hljs.highlightElement(summary);
              }
            );
          }, 250)
        );
      },
    });
  }

  postRender() {
    hljs.highlightAll();
  }
}

class DashboardView extends View {
  constructor() {
    super(HomeURLPath, "dashboard");
  }

  async fetchData(url) {
    return fetchJSON(`/functions`);
  }

  render(rootElementSelector, data) {
    micro(rootElementSelector, this.templateId, data, (el, d) => {
      const conj = el.querySelector("[data-conjure]");
      conj.setAttribute("id", `id-${d.id}`);
      conj.setAttribute("data-conjure", JSON.stringify(d.meta));
      return el;
    });
  }

  postRender() {
    conjure({});
  }
}

class NotFoundView extends View {
  constructor() {
    super(URLPath, "not-found");
  }

  async fetchData(url) {
    return {};
  }

  postRender() {}
}

const views = [new DashboardView(), new FunctionDetailView()];

/**
 *
 * @param {URL} url
 */
const selectAndRenderView = async (url) => {
  const view = views.find((v) => v.urlClass.fromURL(url));

  const selectedView = view || new NotFoundView();

  changeView(
    selectedView.urlClass.fromURL(url).relativeUrl,
    selectedView.fetchData.bind(selectedView),
    ".container",
    selectedView.render.bind(selectedView),
    selectedView.postRender.bind(selectedView)
  );
};

const renderView = async (selectedView, path) => {
  changeView(
    new URL(path, new URL(window.location.href).origin),
    selectedView.fetchData.bind(selectedView),
    ".container",
    selectedView.render.bind(selectedView),
    selectedView.postRender.bind(selectedView)
  );
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

  const { key, public_uri, content_type, feed_uri, func_identifier } =
    metaData === null
      ? JSON.parse(element.getAttribute("data-conjure"))
      : metaData;

  const contentTypeToRenderClass = {
    "application/tensor+octet-stream": TensorView,
    "application/time-series+octet-stream": SeriesView,
    "application/tensor-movie+octet-stream": TensorMovieView,
    "audio/wav": AudioView,
    "text/plain": TextView,
  };

  const contentTypeToRootElementType = {
    "application/tensor+octet-stream": "canvas",
    "application/tensor-movie+octet-stream": "canvas",
    "application/time-series+octet-stream": "div",
    "audio/wav": "canvas",
    "text/plain": "div",
  };

  const renderer = contentTypeToRenderClass[content_type];
  const rootElement = contentTypeToRootElementType[content_type];

  const root = element;
  root.innerHTML = "";

  const container = document.createElement(rootElement);
  container.style.width = style.width;
  container.style.height = style.height;
  container.addEventListener("click", async () => {
    renderView(
      views.find((v) => v.constructor.name === FunctionDetailView.name),
      `/dashboard/functions/${func_identifier}`
    );
  });
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
        const index = onlyNew.length - 1;
        const { key, timestamp } = onlyNew[index];
        element.id = `id-${key}`;
        const origMetadata = JSON.parse(element.getAttribute("data-conjure"));
        const parts = origMetadata.public_uri.split("/").slice(0, -1);
        const newPublicUri = [...parts, key].join("/");

        const newMetaData = {
          ...origMetadata,
          public_uri: newPublicUri,
        };

        element.setAttribute("data-conjure", JSON.stringify(newMetaData));
        clearInterval(interval);
        await conjure({
          element,
          newMetaData,
          refreshRate,
          feedOffset: timestamp,
        });
      }
    }, refreshRate);
  }
};

window.addEventListener("popstate", async (event) => {
  const url = new URL(window.location.href);
  await selectAndRenderView(url);
});

document.addEventListener(
  "DOMContentLoaded",
  async () => {
    const url = new URL(window.location.href);
    await selectAndRenderView(url);
  },
  false
);
