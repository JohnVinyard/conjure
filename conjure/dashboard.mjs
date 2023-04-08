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
  const [loc] = location;

  const size = 0.5;

  const color = new THREE.Color(1 * value, 0.5 * value, 0.1 * value);

  const geometry = new THREE.BoxGeometry(size, size, size);
  const material = new THREE.MeshBasicMaterial({
    color,
    opacity: 0.1,
  });
  const cube = new THREE.Mesh(geometry, material);
  scene.add(cube);
  cube.position.x = loc * size;
};

const visit = (typedArray, shape, visitor) => {
  for (let i = 0; i < typedArray.length; i++) {
    // TODO: get "shaped" location in array
    const location = [i];
    visitor(typedArray.at(i), location);
  }
};

document.addEventListener(
  "DOMContentLoaded",
  async () => {
    console.log("READY");

    let offset = "";

    // setInterval(() => {
    //   console.log(`fetching with timestamp ${offset}`);
    //   fetch(
    //     "/feed?" +
    //       new URLSearchParams({
    //         offset,
    //       })
    //   ).then(async (resp) => {
    //     const data = await resp.json();
    //     const list = document.getElementById("new");
    //     data.forEach(({ key, timestamp }) => {
    //       list.insertAdjacentHTML(
    //         "afterbegin",
    //         `<li><a target="_blank" href="/results/${key}">${key}</a></li>`
    //       );
    //     });
    //     if (data.length > 0) {
    //       offset = data.slice(-1)[0].timestamp;
    //       console.log(`Updated timestamp to be ${offset}`);
    //     }
    //   });
    // }, 2500);

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
      console.log(rawShape);
      console.log(massagedShape);

      const shape = JSON.parse(massagedShape);
      const arrayData = new (dtypeToConstructor(dtype))(
        headerAndData.slice(2 + headerLen)
      );

      console.log(shape);
      console.log("ARRAY ELEMENTS", arrayData.length);

      visit(arrayData, shape, renderCubeVisitor);
    });
  },
  false
);
