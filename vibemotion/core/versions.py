"""Satu-satunya tempat versi dependensi Remotion didefinisikan.

Semua paket remotion / @remotion/* WAJIB versi sama persis (tanpa ^), dan
zod dipin sesuai yang diminta Remotion, supaya log "Version mismatch" tidak muncul.
Naikkan REMOTION_VERSION di sini saja saat upgrade (cek `npx remotion versions`).
"""

REMOTION_VERSION = "4.0.544"
ZOD_VERSION = "4.6.7"

REMOTION_PACKAGES = [
    "remotion",
    "@remotion/cli",
    "@remotion/transitions",
    "@remotion/shapes",
    "@remotion/paths",
    "@remotion/noise",
    "@remotion/captions",
    "@remotion/media-utils",
    "@remotion/google-fonts",
    "@remotion/gif",
    "@remotion/layout-utils",
]

OTHER_DEPENDENCIES = {
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "@types/react": "18.3.12",
    "@types/react-dom": "18.3.1",
    "typescript": "5.6.3",
    "lucide-react": "0.460.0",
    "canvas-confetti": "1.9.3",
    "zod": ZOD_VERSION,
}

# Paket opsional yang bisa dipasang dari Package Manager di aplikasi.
OPTIONAL_PACKAGES = [
    ("@remotion/animation-utils", "Helper animasi CSS (fade, slide, stagger)"),
    ("@remotion/animated-emoji", "Emoji animasi 3D"),
    ("@remotion/fonts", "Memuat font lokal"),
    ("@remotion/three", "Three.js / 3D (butuh three, @react-three/fiber)"),
    ("@remotion/lottie", "Animasi Lottie"),
    ("@remotion/motion-blur", "Efek motion blur"),
]


def package_json_dependencies() -> dict[str, str]:
    deps = {name: REMOTION_VERSION for name in REMOTION_PACKAGES}
    deps.update(OTHER_DEPENDENCIES)
    return dict(sorted(deps.items()))
