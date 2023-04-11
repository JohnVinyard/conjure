import * as THREE from "three";
import { OrbitControls } from "https://unpkg.com/three@0.139.2/examples/jsm/controls/OrbitControls.js";
import * as d3 from "d3";

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

const audioCache = {};
const context = new (window.AudioContext || window.webkitAudioContext)();

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

document.addEventListener(
  "DOMContentLoaded",
  async () => {
    console.log("READY");

    // list the keys
    const results = await fetch("/");
    const data = await results.json();
    const keysList = document.getElementById("keys");
    keysList.innerHTML = "";
    data.forEach((key) => {
      const li = document.createElement("li");
      li.innerText = key;
      li.onclick = async () => {
        // TensorView.renderURL(`/results/${key}`, "display-canvas");
        AudioView.renderURL(`/results/${key}`, "display-canvas");
      };
      keysList.appendChild(li);
    });
  },
  false
);
