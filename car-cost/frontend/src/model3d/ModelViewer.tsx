/**
 * La maquette du véhicule, liée à l'arbre. Seul fichier qui charge `three`, et
 * seulement quand l'onglet 3D s'ouvre : le reste de l'écran n'en paie pas le
 * poids. Les coordonnées manipulées ici sont de l'affichage, pas des montants.
 */

import { useEffect, useRef, useState } from "react";
import type { PartChange } from "../api/types";
import { colored, highlighted, refOf } from "./selection";

export type ModelViewerProps = {
  /** Le `.glb` servi par l'API. */
  model: ArrayBuffer;
  /** La pièce de la ligne sélectionnée : tous ses emplacements sont surlignés. */
  selectedRef: string | null;
  /** L'écart servi par `body-changes` : ses pièces sont colorées. */
  changes: PartChange[];
  onPick: (ref: string) => void;
};

type Painted = {
  id: string;
  ref: string | null;
  material: import("three").MeshStandardMaterial;
  color: import("three").Color;
};

const CHANGED = 0xf59e0b;
const SELECTED = 0x1d4ed8;
/** Au-delà de ce déplacement (px), un clic est une rotation de la vue, pas une sélection. */
const DRAG = 5;

export function ModelViewer({ model, selectedRef, changes, onPick }: ModelViewerProps) {
  const host = useRef<HTMLDivElement>(null);
  const pick = useRef(onPick);
  pick.current = onPick;
  const [objects, setObjects] = useState<Painted[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const element = host.current!;
    let release = () => {};
    let alive = true;
    (async () => {
      const [THREE, { GLTFLoader }, { OrbitControls }] = await Promise.all([
        import("three"),
        import("three/examples/jsm/loaders/GLTFLoader.js"),
        import("three/examples/jsm/controls/OrbitControls.js"),
      ]);
      const gltf = await new GLTFLoader().parseAsync(model, "");
      if (!alive) return;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0xf3f4f6);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f98, 2));
      const sun = new THREE.DirectionalLight(0xffffff, 2);
      sun.position.set(3, 5, 4);
      scene.add(sun, gltf.scene);

      // Chaque objet reçoit son matériau : surligner un côté ne doit pas
      // repeindre l'autre, qui partage le matériau du fichier.
      const painted: Painted[] = [];
      const originals = new Set<import("three").Material>();
      gltf.scene.traverse((node) => {
        if (!(node instanceof THREE.Mesh)) return;
        let owner: import("three").Object3D | null = node;
        while (owner && refOf(owner.userData) === null) owner = owner.parent;
        originals.add(node.material);
        const material = (node.material as import("three").MeshStandardMaterial).clone();
        node.material = material;
        painted.push({ id: node.uuid, ref: owner ? refOf(owner.userData) : null, material, color: material.color.clone() });
      });

      // Le repère du fichier : X à gauche, Y en haut, Z vers l'avant. Vue de trois quarts avant gauche.
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const center = box.getCenter(new THREE.Vector3());
      const reach = box.getSize(new THREE.Vector3()).length();
      const camera = new THREE.PerspectiveCamera(35, 1, reach / 100, reach * 10);
      camera.position.copy(center).add(new THREE.Vector3(0.7, 0.45, 0.9).multiplyScalar(reach * 1.1));

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(window.devicePixelRatio);
      element.appendChild(renderer.domElement);
      const controls = new OrbitControls(camera, renderer.domElement);
      controls.target.copy(center);
      controls.enableDamping = true;

      const resize = () => {
        const { clientWidth: width, clientHeight: height } = element;
        renderer.setSize(width, height);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      };
      resize();
      const observer = new ResizeObserver(resize);
      observer.observe(element);

      const raycaster = new THREE.Raycaster();
      const refs = new Map(painted.map((o) => [o.id, o.ref]));
      let down = { x: 0, y: 0 };
      const onDown = (event: PointerEvent) => (down = { x: event.clientX, y: event.clientY });
      const onUp = (event: PointerEvent) => {
        if (Math.hypot(event.clientX - down.x, event.clientY - down.y) > DRAG) return;
        const rect = renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1,
        );
        raycaster.setFromCamera(pointer, camera);
        // Le décor (vitres, optiques) ne masque pas la pièce derrière lui.
        const hit = raycaster.intersectObject(gltf.scene).find((h) => refs.get(h.object.uuid));
        if (hit) pick.current(refs.get(hit.object.uuid)!);
      };
      renderer.domElement.addEventListener("pointerdown", onDown);
      renderer.domElement.addEventListener("pointerup", onUp);

      renderer.setAnimationLoop(() => {
        controls.update();
        renderer.render(scene, camera);
      });
      setObjects(painted);

      release = () => {
        renderer.setAnimationLoop(null);
        observer.disconnect();
        controls.dispose();
        renderer.domElement.removeEventListener("pointerdown", onDown);
        renderer.domElement.removeEventListener("pointerup", onUp);
        gltf.scene.traverse((node) => {
          if (node instanceof THREE.Mesh) node.geometry.dispose();
        });
        // Les matériaux du fichier ont été remplacés par leurs copies : les deux se libèrent.
        for (const material of originals) material.dispose();
        for (const o of painted) o.material.dispose();
        renderer.dispose();
        element.removeChild(renderer.domElement);
      };
    })().catch((error: unknown) => alive && setFailure(error instanceof Error ? error.message : String(error)));
    return () => {
      alive = false;
      release();
    };
  }, [model]);

  useEffect(() => {
    if (!objects) return;
    const lit = highlighted(objects, selectedRef);
    const tinted = colored(objects, changes);
    for (const o of objects) {
      o.material.color.set(tinted.has(o.id) ? CHANGED : o.color);
      o.material.emissive.set(lit.has(o.id) ? SELECTED : 0x000000);
    }
  }, [objects, selectedRef, changes]);

  return (
    <div className="model3d">
      <div ref={host} className="model3d__canvas" />
      {failure && <p className="hint">modèle 3D illisible : {failure}</p>}
    </div>
  );
}
