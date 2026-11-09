"""Frozen runtime versions, referential integrity and decoded allocation safety."""

import base64
import struct
import pytest

from plugins.pet_2d.backend.package_archive import stage_archive
from plugins.pet_2d.backend.package_schema import validate_package


def load(tmp_path, avatar_package):
    root = tmp_path / "package"
    manifest = stage_archive(avatar_package.write(), root)
    return validate_package(root, manifest)


@pytest.mark.parametrize("field", ["prepared", "mouth", "hair", "lids"])
def test_unknown_algorithm_version_is_not_silently_ignored(
    tmp_path, avatar_package, field
):
    avatar_package.edit(
        "rig/baked.json", lambda data: data[field].update(version="unrecognized")
    )
    with pytest.raises(ValueError, match="算法版本"):
        load(tmp_path, avatar_package)


def test_rgba_hash_and_runtime_image_dimensions_must_match(tmp_path, avatar_package):
    avatar_package.edit(
        "rig/baked.json",
        lambda data: data["prepared"]["layers"][0]["image"].update(rgbaSha256="0" * 64),
    )
    with pytest.raises(ValueError, match="RGBA"):
        load(tmp_path, avatar_package)


def test_baked_image_reference_cannot_escape_or_disappear(tmp_path, avatar_package):
    avatar_package.edit(
        "rig/baked.json",
        lambda data: data["lids"]["eyes"][0]["skin"]["image"].update(
            file="../../source.png"
        ),
    )
    with pytest.raises(ValueError, match="路径"):
        load(tmp_path, avatar_package)


@pytest.mark.parametrize("fault", ["length", "nan", "index", "vertices"])
def test_mesh_structural_failures_are_rejected_before_rendering(
    tmp_path, avatar_package, fault
):
    def mutate(data):
        hair = data["hair"]["layers"][0]
        if fault == "length":
            hair["rest"] = base64.b64encode(bytes(4)).decode()
        elif fault == "nan":
            hair["freedom"] = base64.b64encode(
                struct.pack("<4f", 0, 0, 1, float("nan"))
            ).decode()
        elif fault == "index":
            hair["layer"] = 999
        else:
            hair.update(nx=65000, ny=65000)

    avatar_package.edit("rig/baked.json", mutate)
    with pytest.raises(ValueError):
        load(tmp_path, avatar_package)


def test_cross_document_inputs_cannot_mix_two_versions(tmp_path, avatar_package):
    avatar_package.edit(
        "rig/baked.json", lambda data: data["inputs"].update(binding="0" * 64)
    )
    with pytest.raises(ValueError, match="输入哈希"):
        load(tmp_path, avatar_package)


def test_nonfinite_diagnostic_fields_are_rejected_too(tmp_path, avatar_package):
    avatar_package.edit(
        "rig/baked.json", lambda data: data.update(diagnostic=float("inf"))
    )
    with pytest.raises(ValueError, match="非有限"):
        load(tmp_path, avatar_package)


@pytest.mark.parametrize(
    "missing",
    ["eye", "choice", "parametric", "articulation", "morph", "interior"],
)
def test_import_gate_requires_the_profile_consumed_by_renderer(
    tmp_path, avatar_package, missing
):
    def mutate(data):
        if missing == "eye":
            del data["prepared"]["anchors"]["eyeR"]
        elif missing == "choice":
            data["mouth"]["choice"]["renderer"] = "morph"
        elif missing in {"parametric", "articulation"}:
            data["mouth"][missing] = None
        elif missing == "morph":
            data["mouth"]["morph"] = True
        else:
            data["mouth"]["interior"] = {"alternate": "atlas"}

    avatar_package.edit("rig/baked.json", mutate)
    # The fixture rebuilds manifest byte counts/hashes, so this exercises semantic admission.
    with pytest.raises(ValueError):
        load(tmp_path, avatar_package)


def test_lid_band_requires_the_renderers_exact_sample_count(tmp_path, avatar_package):
    avatar_package.edit(
        "rig/baked.json",
        lambda data: data["lids"]["eyes"][0]["shape"].update(band=[1, 1]),
    )
    with pytest.raises(ValueError, match="lid.band"):
        load(tmp_path, avatar_package)


@pytest.mark.parametrize("fault", ["zero-opening", "oversized-mouth"])
def test_mouth_positive_limits_match_renderer(tmp_path, avatar_package, fault):
    def mutate(data):
        if fault == "zero-opening":
            data["mouth"]["articulation"]["openPx"] = 0
        else:
            data["mouth"]["parametric"]["fit"]["style"]["halfWidth"] = 16385

    avatar_package.edit("rig/baked.json", mutate)
    with pytest.raises(ValueError, match="数值无效"):
        load(tmp_path, avatar_package)
