// ٢٠٢٦-٠٩-٠٩ (ختم NQ) — تعريف وحدات `three` للفحص النوعيّ.
//
// `three` تُشحن بلا ملفّات تعريف، و`@types/three` غير مثبّتة، فكان الفحص
// النوعيّ (`npx tsc --noEmit`) يتوقّف على أخطاء في «الشبكة» — وهي ضجيج يخفي
// أخطاءً حقيقيّة في بقيّة اللوحة. هذا الملفّ يُسكت الضجيج وحده: لا يلمس
// `Network.tsx` ولا سلوك الشبكة (WebGL لا تُمسّ إلّا بأمر المالك).
//
// الأصناف المُعلَنة هنا هي التي تستعملها «الشبكة» **كأنواع** فعلًا؛ ما يُستعمل
// كقيمة فقط يمرّ عبر فهرس الوحدة. الأنواع مُرخاة عمدًا — الغرض إسكات ضجيج
// مكتبة بلا تعريفات، لا التظاهر بفحصها. إن ثُبّتت `@types/three` يومًا،
// احذف هذا الملفّ: الأنواع الحقيقيّة أدقّ.
declare module 'three' {
  /* eslint-disable @typescript-eslint/no-explicit-any */
  export class Color { constructor(...args: any[]); [k: string]: any }
  export class CanvasTexture { constructor(...args: any[]); [k: string]: any }
  export class Sprite { constructor(...args: any[]); [k: string]: any }
  export class WebGLRenderer { constructor(...args: any[]); [k: string]: any }
  export class Points { constructor(...args: any[]); [k: string]: any }
  export class LineSegments { constructor(...args: any[]); [k: string]: any }
  export class Material { constructor(...args: any[]); [k: string]: any }
  export class BufferAttribute { constructor(...args: any[]); [k: string]: any }
  export class Object3D { constructor(...args: any[]); [k: string]: any }
  export class Vector2 { constructor(...args: any[]); [k: string]: any }
  export class Vector3 { constructor(...args: any[]); [k: string]: any }
  export class Scene { constructor(...args: any[]); [k: string]: any }
  export class PerspectiveCamera { constructor(...args: any[]); [k: string]: any }
  export class Texture { constructor(...args: any[]); [k: string]: any }
  export class BufferGeometry { constructor(...args: any[]); [k: string]: any }
  const _rest: any
  export = _rest
}
declare module 'three/examples/jsm/postprocessing/EffectComposer.js'
declare module 'three/examples/jsm/postprocessing/RenderPass.js'
declare module 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
