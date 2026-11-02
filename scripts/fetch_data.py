#!/usr/bin/env python3
"""Download the one public JUMP field used by the fixture into data/, verifying sha256.

Plate BR00117035, well A01, site 1 of cpg0016-jump source_4 (Cell Painting Gallery, CC0 1.0):
8 raw channel images and the plate's 8 illumination correction files, about 56 MB.
Safe to re-run: files already present with the right hash are kept.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://cellpainting-gallery.s3.amazonaws.com/cpg0016-jump/source_4/images/2021_04_26_Batch1/"
FILES = [  # (path under BASE, bytes, sha256)
    ("illum/BR00117035/BR00117035_IllumAGP.npy", 4665728, "3a1c023c284ef7872c221f569d0f505dc19137a4301738efff49ff8fb309805e"),
    ("illum/BR00117035/BR00117035_IllumBrightfield.npy", 4665728, "65c110e17572c0581f641fc87720a5a8d0e6d2dba3beacd2add8d01d066435e5"),
    ("illum/BR00117035/BR00117035_IllumBrightfield_H.npy", 4665728, "463e50fb0232ef2c92dece171190f65265b76b20ac2c6c29d41531ccf7491c55"),
    ("illum/BR00117035/BR00117035_IllumBrightfield_L.npy", 4665728, "230bee15dd6df398ba49350a933b20118a69da97fa8c2a5c46e8434941ceb585"),
    ("illum/BR00117035/BR00117035_IllumDNA.npy", 4665728, "28a34fa509b29723322752a1cdef6e1dd1c58a1d28e5d27780405513f575989a"),
    ("illum/BR00117035/BR00117035_IllumER.npy", 4665728, "87c18be0358e2d2e15f93d5c1e7b82b0632af0b1a985df1b777f197725237dd0"),
    ("illum/BR00117035/BR00117035_IllumMito.npy", 4665728, "2a934a0aa17a2e1a5c88e3a02c10755ba5d4cd39627aab43cba85174014952ce"),
    ("illum/BR00117035/BR00117035_IllumRNA.npy", 4665728, "de45f3b107b1906eb67ba9814ad6f18ca46d2ffab462f84b3cb78d33f5fc62fc"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch1sk1fk1fl1.tiff", 2437278, "1846172a17c4623619672c03351d2f171947e022a2c6a99395fbf5303c873bcf"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch2sk1fk1fl1.tiff", 2463886, "52d5b3d2f863fba6cd8641dc7bfccd7d1b49d1afe25165c5177d5970d920cc96"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch3sk1fk1fl1.tiff", 2418352, "7565b2aa7564b930f334317c4d38abde723965b777fb91d37cf097159b75f310"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch4sk1fk1fl1.tiff", 2481760, "541de017df6d18c61a9a5f85f20fd71d9b6cfa266d212ea72c9a2b197bd9beff"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch5sk1fk1fl1.tiff", 2017706, "4289ea953db4748dae5eb1028d041f556443c6e4f5e78c0af987cb1d368db677"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch6sk1fk1fl1.tiff", 2477976, "fd44784f7a16487e49acedd77864f34c618076dee1d68a6d7e7a7b9c582e7f79"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch7sk1fk1fl1.tiff", 2452228, "24da1f74e474a2c156ceaadba2a001f1b31105510013544c6c2a91115f857a16"),
    ("images/BR00117035__2021-05-02T16_02_51-Measurement1/Images/r01c01f01p01-ch8sk1fk1fl1.tiff", 2395088, "f505311a171f08797f624a9a248fe0e2f552a89cc0c6ff97c0a201c484c46083"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    out = Path(__file__).resolve().parent.parent / "data"
    out.mkdir(exist_ok=True)
    for rel, size, digest in FILES:
        dest = out / rel.rsplit("/", 1)[1]
        if dest.exists() and sha256(dest) == digest:
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        print(f"fetching {dest.name} ({size / 1e6:.1f} MB)", flush=True)
        urllib.request.urlretrieve(BASE + rel, tmp)
        if sha256(tmp) != digest:
            sys.exit(f"sha256 mismatch for {dest.name}; refusing to use it ({tmp} kept for inspection)")
        tmp.rename(dest)
    print(f"data ok: {len(FILES)} files verified in {out}")


if __name__ == "__main__":
    main()
