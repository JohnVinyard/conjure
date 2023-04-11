import * as THREE from "three";
import { OrbitControls } from "https://unpkg.com/three@0.139.2/examples/jsm/controls/OrbitControls.js";
import * as d3 from "d3";

console.log(d3);

const myCanvas = document.getElementById("display-canvas");

const axes = new THREE.AxesHelper();

const scene = new THREE.Scene();
scene.add(axes);

const camera = new THREE.PerspectiveCamera(
  50,
  myCanvas.offsetWidth / myCanvas.offsetHeight
);
camera.position.set(1, 1, 1);
camera.lookAt(scene.position);

const renderer = new THREE.WebGLRenderer({ canvas: myCanvas });
renderer.setClearColor(0xffffff, 1.0);
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(myCanvas.offsetWidth, myCanvas.offsetHeight);

const orbitControls = new OrbitControls(camera, renderer.domElement);
orbitControls.maxPolarAngle = Math.PI * 0.5;
orbitControls.minDistance = 0.1;
orbitControls.maxDistance = 100;
// orbitControls.autoRotate = true;
// orbitControls.autoRotateSpeed = 1.0;

renderer.setAnimationLoop(() => {
  orbitControls.update();

  renderer.render(scene, camera);
});

const fetchData = async (key) => {
  const resp = await fetch(`/results/${key}`);
  console.log(resp);
};

const dtypeToConstructor = (dtype) => {
  if (dtype === "<f4") {
    return Float32Array;
  }

  throw new Error("Not Implemented");
};

const renderCubeVisitor = (value, location) => {
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

const AUDIO_STEP = 512;

const renderAudioVisitor = (value, location) => {
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

const visit = (typedArray, shape, visitor) => {
  const stride = strides(shape);

  for (let i = 0; i < typedArray.length; i++) {
    const location = computeIndices(i, shape, stride);
    visitor(typedArray.at(i), location);
  }
};

const fetchBinary = (url) => {
  return new Promise(function (resolve, reject) {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", url);
    xhr.responseType = "arraybuffer";
    xhr.onload = function () {
      if (this.status >= 200 && this.status < 300) {
        resolve(xhr.response);
      } else {
        reject(this.status, xhr.statusText);
      }
    };
    xhr.onerror = function () {
      reject(this.status, xhr.statusText);
    };
    xhr.send();
  });
};

const audioCache = {};
const context = new (window.AudioContext || window.webkitAudioContext)();

const fetchAudio = (url, context) => {
  const cached = audioCache[url];
  if (cached !== undefined) {
    return cached;
  }

  const audioBufferPromise = fetchBinary(url).then(function (data) {
    // return new Promise(function (resolve, reject) {
    //   context.decodeAudioData(data, (buffer) => resolve(buffer));
    // });
    return context.decodeAudioData(data);
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

const draw1D = (stride, increment, height, imageData) => {
  for (let i = 0; i < this.containerWidth(); i++) {
    const index = this.featureData.length * this.offsetPercent + i * stride;
    const sample = Math.abs(this.featureData.binaryData[Math.round(index)]);

    // KLUDGE: This assumes that all data will be in range 0-1
    const value = 0.25 + sample;
    const color = `rgba(0, 0, 0, ${value})`;
    this.drawContext.fillStyle = color;

    const size = sample * height;
    this.drawContext.fillRect(
      this.$refs.container.scrollLeft + i,
      (height - size) / 2,
      increment,
      size
    );
  }
};

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
      li.onclick = () => fetchData(key);
      keysList.appendChild(li);
    });

    // document.onclick = () => {
    //   playAudio(`/results/${data[0]}`, context, 0, 10);
    // };

    fetchAudio(`/results/${data[0]}`, context).then((buffer) => {
      const array = buffer.getChannelData(0);
      visit(array, [array.length], renderAudioVisitor);
    });

    // https://numpy.org/devdocs/reference/generated/numpy.lib.format.html

    // fetch data for the first key
    // fetch(`/results/${data[0]}`).then(async (resp) => {
    //   const raw = await resp.arrayBuffer();
    //   const headerAndData = raw.slice(8);

    //   const headerLen = new Uint16Array(headerAndData.slice(0, 2)).at(0);
    //   console.log("HEADER LENGTH", headerLen);

    //   const arr = new Uint8Array(headerAndData.slice(2, 2 + headerLen));
    //   const str = String.fromCharCode(...arr);

    //   const dtypePattern = /('descr':\s+)'([^']+)'/;
    //   const shapePattern = /('shape':\s+)(\([^/)]+\))/;

    //   const dtype = str.match(dtypePattern)[2];
    //   const rawShape = str.match(shapePattern)[2];

    //   const hasTrailingComma = rawShape.slice(-2)[0] === ",";
    //   const truncated = rawShape.slice(1, hasTrailingComma ? -2 : -1);
    //   const massagedShape = `[${truncated}]`;

    //   const shape = JSON.parse(massagedShape);
    //   const arrayData = new (dtypeToConstructor(dtype))(
    //     headerAndData.slice(2 + headerLen)
    //   );

    //   // render tensor
    //   visit(arrayData, shape, renderCubeVisitor);
    // });
  },
  false
);
