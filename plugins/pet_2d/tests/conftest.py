"""Small synthetic packages exercising the actual format without private character art."""

import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

from PIL import Image
import pytest

from plugins.pet_2d.backend.bake_schema import BAKE_VERSIONS


def json_bytes(value):
    """Encode deterministic fixture JSON."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def packed(values):
    """Encode the exact little-endian Float32 bake representation."""
    return base64.b64encode(struct.pack(f"<{len(values)}f", *values)).decode("ascii")


class AvatarFixture:
    """Editable, tiny source package with regenerated file manifest integrity."""

    def __init__(self, workspace: Path):
        self.source = workspace / "private_runtime/imports/pet_2d-pets/avatar.zip"
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.files = {}
        rgba = {}

        def image(name, size=(8, 8)):
            im = Image.new("RGBA", size, (90, 120, 150, 255))
            stream = io.BytesIO()
            im.save(
                stream,
                format="WEBP" if name.endswith(".webp") else "PNG",
                lossless=True,
                exact=True,
            )
            self.files[name] = stream.getvalue()
            rgba[name] = hashlib.sha256(im.tobytes()).hexdigest()

        def ref(name):
            return {"file": name, "rgbaSha256": rgba["rig/" + name]}

        image("source.png")
        image("mouth/open.png", (2, 2))
        for i, size in enumerate(((8, 8), (4, 2), (2, 2))):
            image(f"layers/layer-{i:03}.png", size)
            image(f"rig/layers/{i:03}.webp", size)
        image("rig/baked/000.webp", (4, 2))
        image("rig/baked/001.webp")
        self.files["editable/character.psd"] = (
            b"8BPS\x00\x01"
            + bytes(6)
            + struct.pack(">HIIHH", 4, 8, 8, 8, 3)
            + bytes(14 + 8 * 8 * 4)
        )
        self.files["review.json"] = json_bytes({"state": "synthetic-test"})
        binding_layers = []
        rig_layers = []
        for i, (name, x, y, w, h, phys, side, fade) in enumerate(
            (
                ("back hair", 0, 0, 8, 8, "hair", None, None),
                ("eyelash_l", 1, 2, 4, 2, None, "L", "eyeOpen"),
                ("mouth_open", 3, 5, 2, 2, None, None, "mouthOpen"),
            )
        ):
            binding_layers.append(
                {
                    "id": f"layer-{i:03}",
                    "displayName": name,
                    "role": name,
                    "roleSource": "name-inference",
                    "file": f"layers/layer-{i:03}.png",
                    "bboxXYXY": [x, y, x + w, y + h],
                    "width": w,
                    "height": h,
                    "z": i,
                    "visible": True,
                    "opacity": 1,
                }
            )
            rig_layers.append(
                {
                    "name": name,
                    "source": name,
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "z": i,
                    "depth": 1,
                    "group": "head",
                    "phys": phys,
                    "opacity": 1,
                    "fade": fade,
                    "side": side,
                    "strands": [{"x": 4, "rootY": 0, "tipY": 8}] if phys else None,
                    "image": ref(f"layers/{i:03}.webp"),
                }
            )
        binding = {
            "schema": "prelulu-avatar-binding/v1",
            "canvas": {"width": 8, "height": 8},
            "coordinates": "canvas top-left pixels; bboxXYXY right/bottom exclusive",
            "layerOrder": "bottom-first",
            "layers": binding_layers,
            "sourceRegistration": {
                "kind": "integer-center-square-pad-then-resize",
                "sourceSize": [8, 8],
                "squareSize": [8, 8],
                "paddingLTRB": [0, 0, 0, 0],
                "matrix3x3": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            },
            "mouth": {
                "openFile": "mouth/open.png",
                "rectXYWH": [3, 5, 2, 2],
                "maxWidth": 2,
                "drive": "amplitude-only",
                "phonemes": False,
                "visemes": False,
                "deformation": {
                    "schema": "lip-local/v1",
                    "anchorXY": [4, 6],
                    "angleRadians": 0,
                },
            },
        }
        anchors = {
            "face": {"cx": 4, "cy": 3, "x0": 1, "x1": 7, "y0": 1, "y1": 7},
            "eyeL": {
                "x0": 1,
                "x1": 5,
                "y0": 2,
                "y1": 4,
                "icx": 3,
                "icy": 3,
                "closeY": 3,
            },
            "mouth": {"cx": 4, "cy": 6, "x0": 3, "x1": 5, "y0": 5, "y1": 7},
            "neckPivot": {"cx": 4, "cy": 7},
            "neckTop": 6,
            "neckBottom": 8,
            "bodyPivot": {"cx": 4, "cy": 8},
            "faceScale": 1,
            "hairRootY": 0,
        }
        anchors["eyeR"] = {**anchors["eyeL"], "x0": 4, "x1": 7, "icx": 5.5}
        psd_hash = hashlib.sha256(self.files["editable/character.psd"]).hexdigest()
        rig = {
            "schema": "prelulu-rig-bundle/v1",
            "version": "rig-v1-0000000000000001",
            "builder": {
                "upstream": {
                    "repository": "https://github.com/852wa/Anime2.5DRig",
                    "commit": "7ddbd9943ea3152561b3dc8348fd752c850f3e95",
                },
                "sources": {"rigger.js": "0" * 64},
            },
            "psd": {
                "sha256": psd_hash,
                "bytes": len(self.files["editable/character.psd"]),
            },
            "rig": {
                "canvas": {"w": 8, "h": 8},
                "layers": rig_layers,
                "anchors": anchors,
                "warnings": [],
                "synth": {"eye": False, "mouth": False},
            },
        }
        self.files["binding.json"] = json_bytes(binding)
        self.files["rig/rig.json"] = json_bytes(rig)
        bake = {
            "schema": "prelulu-rig-bake/v1",
            "inputs": {
                "rig": {"version": rig["version"], "psd": psd_hash},
                "binding": hashlib.sha256(self.files["binding.json"]).hexdigest(),
                "source": hashlib.sha256(self.files["source.png"]).hexdigest(),
                "openMouth": hashlib.sha256(self.files["mouth/open.png"]).hexdigest(),
                "profile": {"eyeAlignment": True, "headAttachments": True},
            },
            "prepared": {
                "version": BAKE_VERSIONS["prepared"],
                "layers": deepcopy(rig_layers),
                "anchors": anchors,
            },
            "mouth": {
                "version": BAKE_VERSIONS["mouth"],
                "closed": 2,
                "choice": {"renderer": "parametric"},
                "fit": None,
                "morph": False,
                "interior": None,
                "parametric": {
                    "fit": {
                        "style": {
                            "halfWidth": 1,
                            "lineWidth": 1,
                            "restCurve": 0,
                            "openHeight": 1,
                            "ink": [1, 2, 3],
                            "cavity": [1, 2, 3],
                            "tongue": [1, 2, 3],
                            "teeth": [255, 255, 255],
                        },
                        "origin": {"x": 4, "y": 6},
                        "angle": 0,
                    },
                    "x": 3,
                    "y": 5,
                    "w": 2,
                    "h": 2,
                },
                "articulation": {"openPx": 1, "bound": "mouth_width", "reach": None},
            },
            "hair": {
                "version": BAKE_VERSIONS["hair"],
                "layers": [
                    {
                        "layer": 0,
                        "nx": 1,
                        "ny": 1,
                        "version": "hair-pins/v3",
                        "kind": "back",
                        "strands": [
                            {
                                "x": 4,
                                "rootY": 0,
                                "tipY": 8,
                                "attachY": 0,
                                "hang": 8,
                                "restsOn": None,
                                "freedom": 1,
                            }
                        ],
                        "rest": packed([0, 0, 8, 0, 0, 8, 8, 8]),
                        "weights": packed([1] * 4),
                        "freedom": packed([0, 0, 1, 1]),
                        "hang": packed([0, 0, 8, 8]),
                        "cap": packed([0, 0, 2, 2]),
                        "lo": packed([0, 0, -2, -2]),
                        "hi": packed([0, 0, 2, 2]),
                    }
                ],
            },
            "lids": {
                "version": BAKE_VERSIONS["lids"],
                "eyes": [
                    {
                        "side": "L",
                        "shape": {
                            "scale": 2,
                            "low": -2,
                            "high": 2,
                            "lower": [0, 0, 0],
                            "edge": [-1, 0, 0],
                            "smile": [-1, 0, 0],
                            "rise": 1,
                            "opening": 1,
                            "band": [1] * 65,
                            "weight": 1,
                            "colour": [1, 2, 3],
                        },
                        "lashes": [
                            {
                                "layer": 1,
                                "ink": None,
                                "rest": {
                                    "x": 1,
                                    "y": 2,
                                    "w": 4,
                                    "h": 2,
                                    "image": ref("baked/000.webp"),
                                },
                            }
                        ],
                        "skin": {
                            "x": 0,
                            "y": 0,
                            "w": 8,
                            "h": 8,
                            "image": ref("baked/001.webp"),
                        },
                    }
                ],
            },
        }
        self.files["rig/baked.json"] = json_bytes(bake)
        self.manifest = {
            "schema": "prelulu-avatar-package/v1",
            "character": "synthetic-character",
            "name": "Synthetic Avatar",
            "version": "test-v1",
            "binding": "binding.json",
            "review": "review.json",
            "inputHashes": {
                "source": "a" * 64,
                "psd": psd_hash,
                "mouth": bake["inputs"]["openMouth"],
            },
            "capabilities": {
                "editablePSD": True,
                "cubism": False,
                "amplitudeOnly": True,
                "visemes": False,
            },
        }

    def edit(self, name, mutate):
        """Edit one document while leaving unrelated bytes intact."""
        document = json.loads(self.files[name])
        mutate(document)
        self.files[name] = json_bytes(document)

    def write(self, manifest_change=None, *, extra=None):
        """Write a self-consistent package unless a test requests an explicit fault."""
        manifest = deepcopy(self.manifest)
        records = {}
        for name, data in self.files.items():
            entry = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            if name.endswith((".png", ".webp")):
                with Image.open(io.BytesIO(data)) as image:
                    entry.update(dimensions=list(image.size), mode=image.mode)
            records[name] = entry
        manifest["files"] = records
        if manifest_change:
            manifest_change(manifest)
        with zipfile.ZipFile(
            self.source, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr("package/manifest.json", json_bytes(manifest))
            for name, data in self.files.items():
                archive.writestr("package/" + name, data)
            for name, data in (extra or {}).items():
                info = zipfile.ZipInfo(name)
                info.filename = (
                    name  # Keep hostile Windows paths unchanged for boundary tests.
                )
                archive.writestr(info, data)
        return self.source


@pytest.fixture
def avatar_package(tmp_path):
    """A fresh synthetic package whose source is in the provider's staging scope."""
    return AvatarFixture(tmp_path)
