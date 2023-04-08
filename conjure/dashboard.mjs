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
orbitControls.autoRotate = true;
orbitControls.autoRotateSpeed = 1.0;

renderer.setAnimationLoop(() => {
  orbitControls.update();

  renderer.render(scene, camera);
});

const fetchData = async (key) => {
  const resp = await fetch(`/results/${key}`);
  console.log(resp);
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


      console.log("HEADER");
      console.log(str);

    });
  },
  false
);
