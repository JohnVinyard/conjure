import * as THREE from "three";
import { OrbitControls } from "https://unpkg.com/three@0.139.2/examples/jsm/controls/OrbitControls.js";

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

    // https://numpy.org/devdocs/reference/generated/numpy.lib.format.html

    // fetch data for the first key
    fetch(`/results/${data[0]}`).then(async (resp) => {
      const raw = await resp.arrayBuffer();
      const headerAndData = raw.slice(8);

      const headerLen = new Uint16Array(headerAndData.slice(0, 2)).at(0);
      console.log("HEADER LENGTH", headerLen);

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

      visit(arrayData, shape, renderCubeVisitor);
    });
  },
  false
);
