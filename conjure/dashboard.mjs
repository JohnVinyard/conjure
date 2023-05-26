import * as THREE from "https://unpkg.com/three@0.139.2/build/three.module.js";
import { OrbitControls } from "https://unpkg.com/three@0.139.2/examples/jsm/controls/OrbitControls.js";
import { select } from "https://cdn.jsdelivr.net/npm/d3-selection@3/+esm";
import { scaleLinear } from "https://cdn.jsdelivr.net/npm/d3-scale@3/+esm";
import {
  axisBottom,
  axisLeft,
} from "https://cdn.jsdelivr.net/npm/d3-axis@3/+esm";
import { line } from "https://cdn.jsdelivr.net/npm/d3-shape@3/+esm";

const COLOR_MAP = [
  [0.050383, 0.029803, 0.527975],
  [0.063536, 0.028426, 0.533124],
  [0.075353, 0.027206, 0.538007],
  [0.086222, 0.026125, 0.542658],
  [0.096379, 0.025165, 0.547103],
  [0.10598, 0.024309, 0.551368],
  [0.115124, 0.023556, 0.555468],
  [0.123903, 0.022878, 0.559423],
  [0.132381, 0.022258, 0.56325],
  [0.140603, 0.021687, 0.566959],
  [0.148607, 0.021154, 0.570562],
  [0.156421, 0.020651, 0.574065],
  [0.16407, 0.020171, 0.577478],
  [0.171574, 0.019706, 0.580806],
  [0.17895, 0.019252, 0.584054],
  [0.186213, 0.018803, 0.587228],
  [0.193374, 0.018354, 0.59033],
  [0.200445, 0.017902, 0.593364],
  [0.207435, 0.017442, 0.596333],
  [0.21435, 0.016973, 0.599239],
  [0.221197, 0.016497, 0.602083],
  [0.227983, 0.016007, 0.604867],
  [0.234715, 0.015502, 0.607592],
  [0.241396, 0.014979, 0.610259],
  [0.248032, 0.014439, 0.612868],
  [0.254627, 0.013882, 0.615419],
  [0.261183, 0.013308, 0.617911],
  [0.267703, 0.012716, 0.620346],
  [0.274191, 0.012109, 0.622722],
  [0.280648, 0.011488, 0.625038],
  [0.287076, 0.010855, 0.627295],
  [0.293478, 0.010213, 0.62949],
  [0.299855, 0.009561, 0.631624],
  [0.30621, 0.008902, 0.633694],
  [0.312543, 0.008239, 0.6357],
  [0.318856, 0.007576, 0.63764],
  [0.32515, 0.006915, 0.639512],
  [0.331426, 0.006261, 0.641316],
  [0.337683, 0.005618, 0.643049],
  [0.343925, 0.004991, 0.64471],
  [0.35015, 0.004382, 0.646298],
  [0.356359, 0.003798, 0.64781],
  [0.362553, 0.003243, 0.649245],
  [0.368733, 0.002724, 0.650601],
  [0.374897, 0.002245, 0.651876],
  [0.381047, 0.001814, 0.653068],
  [0.387183, 0.001434, 0.654177],
  [0.393304, 0.001114, 0.655199],
  [0.399411, 0.000859, 0.656133],
  [0.405503, 0.000678, 0.656977],
  [0.41158, 0.000577, 0.65773],
  [0.417642, 0.000564, 0.65839],
  [0.423689, 0.000646, 0.658956],
  [0.429719, 0.000831, 0.659425],
  [0.435734, 0.001127, 0.659797],
  [0.441732, 0.00154, 0.660069],
  [0.447714, 0.00208, 0.66024],
  [0.453677, 0.002755, 0.66031],
  [0.459623, 0.003574, 0.660277],
  [0.46555, 0.004545, 0.660139],
  [0.471457, 0.005678, 0.659897],
  [0.477344, 0.00698, 0.659549],
  [0.48321, 0.00846, 0.659095],
  [0.489055, 0.010127, 0.658534],
  [0.494877, 0.01199, 0.657865],
  [0.500678, 0.014055, 0.657088],
  [0.506454, 0.016333, 0.656202],
  [0.512206, 0.018833, 0.655209],
  [0.517933, 0.021563, 0.654109],
  [0.523633, 0.024532, 0.652901],
  [0.529306, 0.027747, 0.651586],
  [0.534952, 0.031217, 0.650165],
  [0.54057, 0.03495, 0.64864],
  [0.546157, 0.038954, 0.64701],
  [0.551715, 0.043136, 0.645277],
  [0.557243, 0.047331, 0.643443],
  [0.562738, 0.051545, 0.641509],
  [0.568201, 0.055778, 0.639477],
  [0.573632, 0.060028, 0.637349],
  [0.579029, 0.064296, 0.635126],
  [0.584391, 0.068579, 0.632812],
  [0.589719, 0.072878, 0.630408],
  [0.595011, 0.07719, 0.627917],
  [0.600266, 0.081516, 0.625342],
  [0.605485, 0.085854, 0.622686],
  [0.610667, 0.090204, 0.619951],
  [0.615812, 0.094564, 0.61714],
  [0.620919, 0.098934, 0.614257],
  [0.625987, 0.103312, 0.611305],
  [0.631017, 0.107699, 0.608287],
  [0.636008, 0.112092, 0.605205],
  [0.640959, 0.116492, 0.602065],
  [0.645872, 0.120898, 0.598867],
  [0.650746, 0.125309, 0.595617],
  [0.65558, 0.129725, 0.592317],
  [0.660374, 0.134144, 0.588971],
  [0.665129, 0.138566, 0.585582],
  [0.669845, 0.142992, 0.582154],
  [0.674522, 0.147419, 0.578688],
  [0.67916, 0.151848, 0.575189],
  [0.683758, 0.156278, 0.57166],
  [0.688318, 0.160709, 0.568103],
  [0.69284, 0.165141, 0.564522],
  [0.697324, 0.169573, 0.560919],
  [0.701769, 0.174005, 0.557296],
  [0.706178, 0.178437, 0.553657],
  [0.710549, 0.182868, 0.550004],
  [0.714883, 0.187299, 0.546338],
  [0.719181, 0.191729, 0.542663],
  [0.723444, 0.196158, 0.538981],
  [0.72767, 0.200586, 0.535293],
  [0.731862, 0.205013, 0.531601],
  [0.736019, 0.209439, 0.527908],
  [0.740143, 0.213864, 0.524216],
  [0.744232, 0.218288, 0.520524],
  [0.748289, 0.222711, 0.516834],
  [0.752312, 0.227133, 0.513149],
  [0.756304, 0.231555, 0.509468],
  [0.760264, 0.235976, 0.505794],
  [0.764193, 0.240396, 0.502126],
  [0.76809, 0.244817, 0.498465],
  [0.771958, 0.249237, 0.494813],
  [0.775796, 0.253658, 0.491171],
  [0.779604, 0.258078, 0.487539],
  [0.783383, 0.2625, 0.483918],
  [0.787133, 0.266922, 0.480307],
  [0.790855, 0.271345, 0.476706],
  [0.794549, 0.27577, 0.473117],
  [0.798216, 0.280197, 0.469538],
  [0.801855, 0.284626, 0.465971],
  [0.805467, 0.289057, 0.462415],
  [0.809052, 0.293491, 0.45887],
  [0.812612, 0.297928, 0.455338],
  [0.816144, 0.302368, 0.451816],
  [0.819651, 0.306812, 0.448306],
  [0.823132, 0.311261, 0.444806],
  [0.826588, 0.315714, 0.441316],
  [0.830018, 0.320172, 0.437836],
  [0.833422, 0.324635, 0.434366],
  [0.836801, 0.329105, 0.430905],
  [0.840155, 0.33358, 0.427455],
  [0.843484, 0.338062, 0.424013],
  [0.846788, 0.342551, 0.420579],
  [0.850066, 0.347048, 0.417153],
  [0.853319, 0.351553, 0.413734],
  [0.856547, 0.356066, 0.410322],
  [0.85975, 0.360588, 0.406917],
  [0.862927, 0.365119, 0.403519],
  [0.866078, 0.36966, 0.400126],
  [0.869203, 0.374212, 0.396738],
  [0.872303, 0.378774, 0.393355],
  [0.875376, 0.383347, 0.389976],
  [0.878423, 0.387932, 0.3866],
  [0.881443, 0.392529, 0.383229],
  [0.884436, 0.397139, 0.37986],
  [0.887402, 0.401762, 0.376494],
  [0.89034, 0.406398, 0.37313],
  [0.89325, 0.411048, 0.369768],
  [0.896131, 0.415712, 0.366407],
  [0.898984, 0.420392, 0.363047],
  [0.901807, 0.425087, 0.359688],
  [0.904601, 0.429797, 0.356329],
  [0.907365, 0.434524, 0.35297],
  [0.910098, 0.439268, 0.34961],
  [0.9128, 0.444029, 0.346251],
  [0.915471, 0.448807, 0.34289],
  [0.918109, 0.453603, 0.339529],
  [0.920714, 0.458417, 0.336166],
  [0.923287, 0.463251, 0.332801],
  [0.925825, 0.468103, 0.329435],
  [0.928329, 0.472975, 0.326067],
  [0.930798, 0.477867, 0.322697],
  [0.933232, 0.48278, 0.319325],
  [0.93563, 0.487712, 0.315952],
  [0.93799, 0.492667, 0.312575],
  [0.940313, 0.497642, 0.309197],
  [0.942598, 0.502639, 0.305816],
  [0.944844, 0.507658, 0.302433],
  [0.947051, 0.512699, 0.299049],
  [0.949217, 0.517763, 0.295662],
  [0.951344, 0.52285, 0.292275],
  [0.953428, 0.52796, 0.288883],
  [0.95547, 0.533093, 0.28549],
  [0.957469, 0.53825, 0.282096],
  [0.959424, 0.543431, 0.278701],
  [0.961336, 0.548636, 0.275305],
  [0.963203, 0.553865, 0.271909],
  [0.965024, 0.559118, 0.268513],
  [0.966798, 0.564396, 0.265118],
  [0.968526, 0.5697, 0.261721],
  [0.970205, 0.575028, 0.258325],
  [0.971835, 0.580382, 0.254931],
  [0.973416, 0.585761, 0.25154],
  [0.974947, 0.591165, 0.248151],
  [0.976428, 0.596595, 0.244767],
  [0.977856, 0.602051, 0.241387],
  [0.979233, 0.607532, 0.238013],
  [0.980556, 0.613039, 0.234646],
  [0.981826, 0.618572, 0.231287],
  [0.983041, 0.624131, 0.227937],
  [0.984199, 0.629718, 0.224595],
  [0.985301, 0.63533, 0.221265],
  [0.986345, 0.640969, 0.217948],
  [0.987332, 0.646633, 0.214648],
  [0.98826, 0.652325, 0.211364],
  [0.989128, 0.658043, 0.2081],
  [0.989935, 0.663787, 0.204859],
  [0.990681, 0.669558, 0.201642],
  [0.991365, 0.675355, 0.198453],
  [0.991985, 0.681179, 0.195295],
  [0.992541, 0.68703, 0.19217],
  [0.993032, 0.692907, 0.189084],
  [0.993456, 0.69881, 0.186041],
  [0.993814, 0.704741, 0.183043],
  [0.994103, 0.710698, 0.180097],
  [0.994324, 0.716681, 0.177208],
  [0.994474, 0.722691, 0.174381],
  [0.994553, 0.728728, 0.171622],
  [0.994561, 0.734791, 0.168938],
  [0.994495, 0.74088, 0.166335],
  [0.994355, 0.746995, 0.163821],
  [0.994141, 0.753137, 0.161404],
  [0.993851, 0.759304, 0.159092],
  [0.993482, 0.765499, 0.156891],
  [0.993033, 0.77172, 0.154808],
  [0.992505, 0.777967, 0.152855],
  [0.991897, 0.784239, 0.151042],
  [0.991209, 0.790537, 0.149377],
  [0.990439, 0.796859, 0.14787],
  [0.989587, 0.803205, 0.146529],
  [0.988648, 0.809579, 0.145357],
  [0.987621, 0.815978, 0.144363],
  [0.986509, 0.822401, 0.143557],
  [0.985314, 0.828846, 0.142945],
  [0.984031, 0.835315, 0.142528],
  [0.982653, 0.841812, 0.142303],
  [0.98119, 0.848329, 0.142279],
  [0.979644, 0.854866, 0.142453],
  [0.977995, 0.861432, 0.142808],
  [0.976265, 0.868016, 0.143351],
  [0.974443, 0.874622, 0.144061],
  [0.97253, 0.88125, 0.144923],
  [0.970533, 0.887896, 0.145919],
  [0.968443, 0.894564, 0.147014],
  [0.966271, 0.901249, 0.14818],
  [0.964021, 0.90795, 0.14937],
  [0.961681, 0.914672, 0.15052],
  [0.959276, 0.921407, 0.151566],
  [0.956808, 0.928152, 0.152409],
  [0.954287, 0.934908, 0.152921],
  [0.951726, 0.941671, 0.152925],
  [0.949151, 0.948435, 0.152178],
  [0.946602, 0.95519, 0.150328],
  [0.944152, 0.961916, 0.146861],
  [0.941896, 0.96859, 0.140956],
  [0.940015, 0.975158, 0.131326],
];

for (let i = 0; i < COLOR_MAP.length; i++) {
  COLOR_MAP[i][0] = Math.floor(COLOR_MAP[i][0] * 255);
  COLOR_MAP[i][1] = Math.floor(COLOR_MAP[i][1] * 255);
  COLOR_MAP[i][2] = Math.floor(COLOR_MAP[i][2] * 255);
}

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
    // const axes = new THREE.AxesHelper();

    const scene = new THREE.Scene();
    // scene.add(axes);

    const camera = new THREE.PerspectiveCamera(
      50,
      myCanvas.offsetWidth / myCanvas.offsetHeight
    );
    camera.position.set(...cameraPosition);
    this.camera = camera;

    const renderer = new THREE.WebGLRenderer({ canvas: myCanvas });
    renderer.setClearColor(0xeeeeee, 1.0);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(myCanvas.offsetWidth, myCanvas.offsetHeight);
    this.renderer = renderer;

    // this.setupOrbitControls();

    const clock = new THREE.Clock(true);

    // const directionalLight = new THREE.DirectionalLight(0xffffff, 0.9);
    const directionalLight = new THREE.AmbientLight(0xffffff);
    directionalLight.position.x = 0;
    directionalLight.position.y = 0;
    directionalLight.position.z = -10;
    scene.add(directionalLight);

    this.scene = scene;
    this.clock = clock;

    this.elapsedTime = 0;

    this.sceneUpdater = null;

    this.isStarted = false;
  }

  setCameraPosition(pos) {
    this.camera.position.set(pos);
  }

  setupOrbitControls() {
    const orbitControls = new OrbitControls(
      this.camera,
      this.renderer.domElement
    );
    orbitControls.enablePan = true;
    orbitControls.enableRotate = true;
    // orbitControls.minPolarAngle = -Math.PI;
    // orbitControls.maxPolarAngle = Math.PI;
    orbitControls.minDistance = 0.1;
    orbitControls.maxDistance = 100;
    this.orbitControls = orbitControls;
  }

  get nChilidren() {
    return this.scene.children.length;
  }

  childAt(index) {
    return this.scene.children[index];
  }

  getObjectByName(name) {
    return this.scene.getObjectByName(name);
  }

  traverseChildren(func) {
    this.scene.children.forEach(func);
  }

  clear() {
    while (this.scene.children.length) {
      this.scene.remove(this.scene.children[0]);
    }
  }

  start() {
    this.isStarted = true;

    this.renderer.setAnimationLoop(() => {
      this.elapsedTime += this.clock.getDelta();

      if (this.sceneUpdater !== null) {
        this.sceneUpdater(this.elapsedTime);
      }
      // this.orbitControls.update();
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
    return view;
  }

  render() {
    // Build a template here
    const template = document.createElement("template");
    const div = document.createElement("div");
    const pre = document.createElement("pre");
    pre.innerText = "${this}";
    div.appendChild(pre);
    template.content.appendChild(div);
    micro(`#${this.elementId}`, template, this.tensor);
  }
}

class BasicAudioView {
  constructor(elementId, tensor, url, stepSize = 512) {
    this.elementId = elementId;
    this.stepSize = stepSize;
    this.init(tensor, url);
  }

  init(tensor, url) {
    this.element.removeEventListener("click", this.clickHandler);
    this.tensor = tensor;
    this.url = url;
    this.playStartTime = null;
    this.clickHandler = () => {
      playAudio(url, context, 0, undefined, () => {});
    };
    this.element.addEventListener("click", this.clickHandler);
  }

  static async renderURL(url, elementId, existingView = null) {
    const rawData = await fetchAudio(url, context);
    const samplerate = rawData.sampleRate;
    const channelData = rawData.getChannelData(0);
    const data = new TensorData(channelData, [channelData.length], {
      samplerate,
    });
    const view = existingView || new BasicAudioView(elementId, data, url);
    view.init(data, url);
    view.render();
    return view;
  }

  get samplerate() {
    return this.tensor.metadata.samplerate;
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  render() {
    const width = this.element.width;
    const height = this.element.height;

    const nElements = Math.floor(this.tensor.shape[0] / this.stepSize);
    const sampleWidth = width / nElements;

    const ctxt = this.element.getContext("2d");
    ctxt.clearRect(0, 0, width, height);

    this.tensor.visit((value, location, scene) => {
      const [x, y, z] = location;

      if (x % this.stepSize !== 0) {
        return;
      }

      const pos = sampleWidth * Math.floor(x / this.stepSize);
      const h = height * value;
      const midline = height / 2;

      const colorIndex = Math.floor(Math.abs(value) * 255);
      const [r, g, b] = COLOR_MAP[colorIndex];

      ctxt.fillStyle = `rgb(${r}, ${g}, ${b})`;
      ctxt.fillRect(pos, midline - h / 2, sampleWidth, h);
    });
  }
}

class BasicSpectrogramView {
  constructor(elementId, tensor) {
    this.elementId = elementId;
    this.tensor = tensor;
  }

  get element() {
    return document.getElementById(this.elementId);
  }

  static async renderURL(url, elementId) {
    const data = await TensorData.fromURL(url);
    const view = new BasicSpectrogramView(elementId, data);
    view.render();
    return view;
  }

  render() {
    // pixel space
    const width = this.element.width;
    const height = this.element.height;

    // feature space
    const [w, h] = this.tensor.shape;

    const ctxt = this.element.getContext("2d");
    ctxt.clearRect(0, 0, width, height);

    const imageData = ctxt.getImageData(0, 0, width, height);

    const timeRatio = w / width;
    const featureRatio = h / height;

    const stride = 4;

    for (let i = 0; i < imageData.data.length; i += stride) {
      try {
        // pixel space
        const x = (i / stride) % imageData.width;
        const y = Math.floor(i / stride / imageData.width);

        // feature space
        const timeIndex = Math.floor(x * timeRatio);
        // since the coordinate system goes from top to bottom, we'll need to
        // invert the order we draw features in
        const featureIndex = h - 1 - Math.floor(y * featureRatio);

        const row = this.tensor.getElement(timeIndex);
        const val = row.getElement(featureIndex);

        const intensity = Math.min(255, Math.floor(Math.abs(val) * 255));
        imageData.data[i] = COLOR_MAP[intensity][0];
        imageData.data[i + 1] = COLOR_MAP[intensity][1];
        imageData.data[i + 2] = COLOR_MAP[intensity][2];
        imageData.data[i + 3] = 255;
      } catch (err) {
        console.warn(err);
      }
    }

    ctxt.putImageData(imageData, 0, 0);
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
    return view;
  }

  initScene() {
    const texture = this.textureAtPosition(0);

    const [_, width, height] = this.tensor.shape;

    const ratio = width / height;

    const w = 0.5;
    const h = w * ratio;

    const geometry = new THREE.PlaneBufferGeometry(w, h, width / 4, height / 4);

    const material = new THREE.MeshStandardMaterial({
      color: 0x000000,
      displacementMap: texture,
      side: THREE.DoubleSide,
      roughness: 1,
      metalness: 0,
      depthTest: true,
      depthWrite: true,
      wireframe: true,
    });

    material.needsUpdate = true;

    const cube = new THREE.Mesh(geometry, material);
    cube.name = "plane";
    cube.position.x = 0;
    cube.position.y = 0;
    cube.position.z = 0;

    this.world.scene.add(cube);

    const parent = this.element.parentNode;
    const xLabel = document.createElement("div");
    xLabel.innerText = "Frequency";
    xLabel.style = `
      position: absolute;
      top: 15%;
      left: 42%;
      
    `;

    const yLabel = document.createElement("div");
    yLabel.style = `
      position: absolute;
      top: 45%;
      left: 25%;
      writing-mode: vertical-rl;
      text-orientation: mixed;
    `;
    yLabel.innerText = "Periodicity";

    parent.insertBefore(xLabel, this.element);
    parent.insertBefore(yLabel, this.element);
  }

  render() {
    // set up the world and store a reference
    if (!this.world) {
      const world = new World(this.element, [0, 0, 1.5]);
      this.world = world;
    } else {
      this.world.clear();
    }

    // render the initial scene
    this.initScene();

    this.world.sceneUpdater = (elapsedTime) => {
      if (!this.playStartTime) {
        return;
      }

      const currentTime = elapsedTime - this.playStartTime;
      const currentFrame = Math.round(currentTime * this.samplerate);

      const texture = this.textureAtPosition(currentFrame);

      const plane = this.world.getObjectByName("plane");

      const material = plane.material;
      material.displacementMap = texture;
      material.needsUpdate = true;
    };

    if (this.clickHandler) {
      this.element.removeEventListener("click", this.clickHandler);
    }
    this.element.addEventListener("click", this.clickHandler);

    if (!this.world.isStarted) {
      this.world.start();
    }
  }
}

class TensorView {
  constructor(elementId, tensor) {
    this.elementId = elementId;
    this.tensor = tensor;
    this.world = null;
  }

  static async renderURL(url, elementId, existingView = null) {
    const data = await TensorData.fromURL(url);
    const view = existingView || new TensorView(elementId, data);
    view.tensor = data;
    view.render();
    return view;
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
    if (!this.world) {
      // set up the world and store a reference
      const world = new World(this.element, [50, 0, 50]);
      this.world = world;
    } else {
      this.world.clear();
    }

    const visitor = this.buildVisitor();

    // render the initial scene
    this.tensor.visit(visitor, this.world.scene);

    if (!this.world.isStarted) {
      this.world.start();
    }
  }
}

class SeriesView {
  constructor(elementId, tensor, maxSamples = 500) {
    this.elementId = elementId;
    this.tensor = tensor;
    this.maxSamples = maxSamples;
  }

  static async renderURL(url, elementId, existingView = null) {
    const data = await TensorData.fromURL(url);
    const view = existingView || new SeriesView(elementId, data);
    view.tensor = data;
    view.render();
    return view;
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
      .style("background-color", "#000")
      .append("g")
      .attr("transform", `translate(50, -10)`);

    // Add X axis
    const x = scaleLinear().domain([0, size]).range([0, width]);

    svg
      .append("g")
      .attr("transform", `translate(0, ${height})`)
      .attr("class", "axis")
      .call(axisBottom(x));

    const min = Math.min(...this.tensor.data);
    const max = Math.max(...this.tensor.data);

    // Add Y axis
    const y = scaleLinear().domain([min, max]).range([height, 0]);

    svg.append("g").call(axisLeft(y)).attr("class", "axis");

    // render lines for each "channel"
    for (let i = 0; i < nChannels; i++) {
      const index = Math.floor(Math.random() * COLOR_MAP.length);
      const [r, g, b] = COLOR_MAP[index];
      const color = `rgb(${r}, ${g}, ${b})`;

      const data = this.tensor
        .getChannelData(i)
        .slice(-this.maxSamples)
        .map((value, index) => ({ value, index }));

      svg
        .append("path")
        .datum(data)
        .attr("fill", "none")
        .attr("stroke", color)
        .attr("stroke-width", 2)
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

  const template =
    typeof templateId === "string"
      ? document.getElementById(templateId)
      : templateId;
    

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
  constructor(query) {
    super();
    this.query = query;
  }

  /**
   *
   * @param {URL} url
   */
  static fromURL(url) {
    const path = typeof url === "string" ? url : `${url.pathname}${url.search}`;
    const pathAndQuery = path.split("?");
    const q =
      pathAndQuery.length > 1
        ? new URLSearchParams(pathAndQuery.slice(-1)[0])
        : new URLSearchParams();

    const segments = path.split("/").filter((segment) => segment.length);
    if (segments.length === 1 && segments[0].startsWith("dashboard")) {
      return new HomeURLPath(q);
    }
  }

  get relativeUrl() {
    return `/dashboard?${this.query}`;
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
        const totalResults = el.querySelector(".total-results");

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
      const title = el.querySelector("h3");
      title.innerText = d.name;
      conj.setAttribute("id", `id-${d.id}`);
      conj.setAttribute("data-conjure", JSON.stringify(d.meta));

      title.addEventListener("click", async () => {
        renderView(
          views.find((v) => v.constructor.name === FunctionDetailView.name),
          `/dashboard/functions/${d.id}`
        );
      });
      return el;
    });
  }

  postRender() {
    const url = new URL(window.location.href);
    const refreshRate = parseInt(url.searchParams.get("refresh"));

    conjure({ refreshRate: isNaN(refreshRate) ? null : refreshRate });
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

const VIEW_CACHE = {};

// TODO: Conjure should take in a map of overridden cotent-type -> component mappings
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
    // find all the conjure elements in the document and conjure
    // them individually
    const elements = document.querySelectorAll("[data-conjure]");
    for (let i = 0; i < elements.length; i++) {
      const el = elements[i];
      await conjure({ element: el, refreshRate, feedOffset });
    }
    return;
  }

  // extract the data about this specific conjure element
  const { key, public_uri, content_type, feed_uri, func_identifier } =
    metaData === null
      ? JSON.parse(element.getAttribute("data-conjure"))
      : metaData;

  const contentTypeToRenderClass = {
    "application/tensor+octet-stream": BasicSpectrogramView,
    "application/time-series+octet-stream": SeriesView,
    "application/tensor-movie+octet-stream": TensorMovieView,
    "audio/wav": BasicAudioView,
    "text/plain": TextView,
  };

  const contentTypeToRootElementType = {
    "application/tensor+octet-stream": "canvas",
    "application/tensor-movie+octet-stream": "canvas",
    "application/time-series+octet-stream": "div",
    "audio/wav": "canvas",
    "text/plain": "div",
  };

  // here, I need to check if there's already a renderer instance created,
  // update its data, and re-render

  const containerId = `display-${key}`;

  // undefined or an *instance* of a view class
  const existing = VIEW_CACHE[containerId];

  const renderer = contentTypeToRenderClass[content_type];
  const rootElement = contentTypeToRootElementType[content_type];

  const root = element;

  if (!existing) {
    root.innerHTML = "";
    const container = document.createElement(rootElement);
    container.style.width = style.width;
    container.style.height = style.height;
    container.id = containerId;
    root.appendChild(container);
    console.log(`New view for ${containerId}`);
  } else {
    console.log(`Existing view for ${containerId}`);
  }

  const view = await renderer.renderURL(public_uri, containerId, existing);
  VIEW_CACHE[containerId] = view;

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
    // KLUDGE: What's a better way to determine whether
    // this is the "app" or just an included script
    if (url.pathname.includes("dashboard")) {
      await selectAndRenderView(url);
    } else {
      await conjure();
    }
  },
  false
);
