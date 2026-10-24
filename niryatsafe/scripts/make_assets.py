"""Build web assets: subset fonts to woff, draw the PWA icons. Needs fontTools + Pillow (both pure pip packages)."""
import os, sys
from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(ROOT, "web", "public")
FONTS = os.path.join(ROOT, "web", "src", "fonts")
os.makedirs(FONTS, exist_ok=True)
os.makedirs(os.path.join(PUB, "icons"), exist_ok=True)

GF = "/usr/share/fonts/truetype/google-fonts"
LIB = "/usr/share/fonts/truetype/liberation"
TEXT = "".join(chr(c) for c in range(0x20, 0x7F)) + "µ×≤≥±—–·•→←↑↓’‘“”…°§½¼¾€₹✓✗ÀÉÖÜàéöüñ"


def make(src, dst):
    opts = subset.Options()
    opts.flavor = "woff"
    opts.layout_features = ["kern", "liga", "tnum", "lnum", "case"]
    opts.desubroutinize = True
    font = TTFont(src)
    sub = subset.Subsetter(opts)
    sub.populate(text=TEXT)
    sub.subset(font)
    font.flavor = "woff"
    font.save(dst)
    print(os.path.basename(dst), os.path.getsize(dst) // 1024, "KB")


lora = [f for f in os.listdir(GF) if f.lower().startswith("lora") and f.endswith(".ttf")]
lora = sorted(lora)[0] if lora else None
if lora:
    make(os.path.join(GF, lora), os.path.join(FONTS, "lora.woff"))
make(os.path.join(LIB, "LiberationMono-Regular.ttf"), os.path.join(FONTS, "mono-regular.woff"))
make(os.path.join(LIB, "LiberationMono-Bold.ttf"), os.path.join(FONTS, "mono-bold.woff"))

# ---- icons: a green customs stamp "NS" on ledger paper ------------------------------------------------
PAPER, INK, GREEN = (243, 237, 223), (28, 26, 22), (30, 107, 71)
mono_bold = os.path.join(LIB, "LiberationMono-Bold.ttf")


def icon(size, maskable=False):
    S = size * 4
    img = Image.new("RGBA", (S, S), PAPER + (255,))
    d = ImageDraw.Draw(img)
    pad = S * (0.26 if maskable else 0.14)
    box = [pad, pad + S * 0.1, S - pad, S - pad - S * 0.1]
    w = int(S * 0.045)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rectangle(box, outline=GREEN + (255,), width=w)
    inset = w * 2.2
    ld.rectangle([box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset], outline=GREEN + (255,), width=int(w * 0.45))
    f = ImageFont.truetype(mono_bold, int(S * 0.36))
    txt = "NS"
    tw = ld.textlength(txt, font=f)
    ld.text(((S - tw) / 2, S * 0.5 - S * 0.235), txt, font=f, fill=GREEN + (255,))
    layer = layer.rotate(6, resample=Image.BICUBIC, center=(S / 2, S / 2))
    img = Image.alpha_composite(img, layer)
    return img.resize((size, size), Image.LANCZOS).convert("RGB")


icon(192).save(os.path.join(PUB, "icons", "icon-192.png"))
icon(512).save(os.path.join(PUB, "icons", "icon-512.png"))
icon(512, maskable=True).save(os.path.join(PUB, "icons", "maskable-512.png"))
icon(180).save(os.path.join(PUB, "icons", "apple-touch-icon.png"))
with open(os.path.join(PUB, "icons", "favicon.svg"), "w") as fh:
    fh.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#F3EDDF"/>'
             '<g transform="rotate(6 32 32)" fill="none" stroke="#1E6B47"><rect x="8" y="14" width="48" height="36" stroke-width="3"/>'
             '<rect x="13" y="19" width="38" height="26" stroke-width="1"/></g>'
             '<text x="32" y="40" text-anchor="middle" font-family="monospace" font-weight="700" font-size="20" fill="#1E6B47" transform="rotate(6 32 32)">NS</text></svg>')
print("assets ok")
