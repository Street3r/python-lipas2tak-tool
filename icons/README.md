# Icon sets

| Folder | Contents | In the repo |
|---|---|---|
| `retkeily/` | The project's own pictogram set (`scripts/make_icons.py`). Default; MIT licensed. | yes |
| `custom/` | Optional local icon set for your own deployment | **no** (`.gitignore`) |

## Using a custom icon set

Only use icons you have the right to use and distribute: they are embedded in
the generated iconset and KMZ files. Custom icons are kept outside the
repository.

1. Save PNG files (64×64 recommended, transparent background) with these names:

   | File | Feature |
   |---|---|
   | `laavu.png` | lean-to shelter |
   | `kota.png` | hut (kota), turf hut (kammi) |
   | `tupa.png` | wilderness / rental hut |
   | `nuotiopaikka.png` | campfire site |
   | `keittokatos.png` | cooking shelter |
   | `nakotorni.png` | observation tower |
   | `nakoalapaikka.png` | viewpoint |
   | `telttapaikka.png` | camping site |
   | `kaymala.png` | toilet |
   | `opastuspiste.png` | information point |
   | `luontokeskus.png` | nature centre |
   | `puuvaja.png` | woodshed |
   | `vesipiste.png` | well / water point |
   | `rantautumispaikka.png` | landing spot |
   | `pysakointi.png` | parking |

   Missing files fall back to the `retkeily/` set automatically.

2. Enable the set with the environment variable `LIPAS2TAK_ICONS_DIR=<folder>`
   (in docker-lipas-integration: see `.env.example`).

The iconset UID stays the same regardless of the set: when a new
`lipas2tak_iconset.zip` is installed in ATAK, markers that were already shared
change their appearance.

To redraw the default set: `pip install Pillow && python scripts/make_icons.py`.
