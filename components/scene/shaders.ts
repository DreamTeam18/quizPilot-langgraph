/**
 * GLSL for the ambient scene.
 *
 * `snoise` is Ashima Arts' / Stefan Gustavson's 3D simplex noise (MIT), the
 * standard implementation used for this kind of vertex displacement.
 */
const SIMPLEX_NOISE = /* glsl */ `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i  = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
             i.z + vec4(0.0, i1.z, i2.z, 1.0))
           + i.y + vec4(0.0, i1.y, i2.y, 1.0))
           + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
}
`;

export const ORB_VERTEX = /* glsl */ `
uniform float uTime;
uniform float uTurbulence;
uniform float uEnergy;

varying vec3 vNormal;
varying vec3 vView;
varying float vDisplace;

${SIMPLEX_NOISE}

float displacement(vec3 p) {
  float t = uTime;
  float base = snoise(p * 1.25 + vec3(0.0, t * 0.35, 0.0));
  float detail = snoise(p * 3.4 - vec3(t * 0.5, 0.0, t * 0.22));
  return base * (0.09 + uTurbulence * 0.26) + detail * (0.02 + uEnergy * 0.03);
}

vec3 displaced(vec3 p) {
  return p + normalize(p) * displacement(p);
}

void main() {
  // Displacing the surface invalidates the supplied normals, so rebuild them
  // from two neighbouring samples; the shading depends on getting this right.
  vec3 axis = abs(normal.y) > 0.99 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 1.0, 0.0);
  vec3 tangent = normalize(cross(normal, axis));
  vec3 bitangent = normalize(cross(normal, tangent));
  float radius = length(position);
  float eps = 0.06;

  vec3 p0 = displaced(position);
  vec3 p1 = displaced(normalize(position + tangent * eps) * radius);
  vec3 p2 = displaced(normalize(position + bitangent * eps) * radius);
  vec3 rebuilt = normalize(cross(p1 - p0, p2 - p0));
  rebuilt *= sign(dot(rebuilt, normal));

  vDisplace = length(p0) - radius;
  vNormal = normalize(normalMatrix * rebuilt);
  vec4 viewPosition = modelViewMatrix * vec4(p0, 1.0);
  vView = -viewPosition.xyz;
  gl_Position = projectionMatrix * viewPosition;
}
`;

export const ORB_FRAGMENT = /* glsl */ `
uniform vec3 uColorA;
uniform vec3 uColorB;
uniform float uPulse;

varying vec3 vNormal;
varying vec3 vView;
varying float vDisplace;

void main() {
  vec3 view = normalize(vView);
  vec3 normal = normalize(vNormal);

  // One key light from the upper left. A pale page needs a solid, shaded form:
  // the rim-lit shell a dark theme relies on simply disappears against white.
  vec3 key = normalize(vec3(-0.45, 0.75, 0.55));
  float lambert = dot(normal, key);
  float wrapped = clamp(lambert * 0.5 + 0.5, 0.0, 1.0);
  float rim = pow(1.0 - clamp(dot(view, normal), 0.0, 1.0), 2.2);

  vec3 base = mix(uColorA, uColorB, smoothstep(-0.2, 0.24, vDisplace));
  base = mix(base, vec3(0.985, 0.99, 1.0), 0.22);
  vec3 color = base * (0.66 + wrapped * 0.28 + clamp(lambert, 0.0, 1.0) * 0.2);
  // The silhouette picks up the page colour so it melts into the background
  // instead of ending on a hard dark edge.
  color = mix(color, vec3(0.96, 0.975, 0.995), rim * 0.45);
  color = mix(color, vec3(1.0), uPulse * 0.2);

  gl_FragColor = vec4(color, 1.0);
  #include <colorspace_fragment>
}
`;

export const PARTICLE_VERTEX = /* glsl */ `
uniform float uTime;
uniform float uSpeed;
uniform float uSize;
uniform float uPixelRatio;

attribute float aScale;
attribute float aOffset;

varying float vFade;

void main() {
  float angle = uTime * uSpeed * (0.05 + aScale * 0.09) + aOffset;
  vec3 p = position;
  float c = cos(angle);
  float s = sin(angle);
  p.xz = mat2(c, -s, s, c) * p.xz;
  p.y += sin(uTime * 0.5 * uSpeed + aOffset) * 0.22;

  vec4 viewPosition = modelViewMatrix * vec4(p, 1.0);
  float depth = max(-viewPosition.z, 0.1);
  // Clamped: an unclamped near point becomes a blob once bloom reaches it.
  gl_PointSize = clamp(uSize * aScale * uPixelRatio * (6.0 / depth), 0.6, 4.0 * uPixelRatio);
  // Fade at both extremes so the field has no visible boundary, and again very
  // close to the camera where a single point would otherwise dominate.
  vFade = smoothstep(22.0, 9.0, depth) * smoothstep(2.4, 4.4, length(p))
        * smoothstep(1.2, 3.2, depth);
  gl_Position = projectionMatrix * viewPosition;
}
`;

export const PARTICLE_FRAGMENT = /* glsl */ `
uniform vec3 uColor;

varying float vFade;

void main() {
  float distance = length(gl_PointCoord - 0.5);
  float alpha = smoothstep(0.5, 0.0, distance) * vFade;
  if (alpha < 0.01) discard;
  gl_FragColor = vec4(uColor, alpha * 0.5);
  #include <colorspace_fragment>
}
`;
