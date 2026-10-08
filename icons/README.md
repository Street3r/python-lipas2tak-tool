# Kuvakesarjat

| Kansio | Sisältö | Repossa |
|---|---|---|
| `retkeily/` | Oma kuvasymbolisarja (`scripts/make_icons.py`). Oletus, vapaasti jaettava. | kyllä |
| `placeholder/` | Vanhat kirjainkuvakkeet | kyllä |
| `luontoon/` | Pilottikäytön Luontoon.fi-/Metsähallitus-kuvakkeet | **ei** (`.gitignore`) |

## Oman sarjan käyttö (esim. Luontoon.fi-kuvakkeet pilotissa)

Metsähallituksen symbolit ovat heidän tekijänoikeudellista materiaaliaan. Niitä
ei lisätä repoon ennen kuin käyttölupa on saatu. Sisäistä pilottia varten
kuvakkeet laitetaan palvelimelle erikseen:

1. Tallenna PNG-tiedostot (suositus 64×64, läpinäkyvä tausta) näillä nimillä:

   | Tiedosto | Kohde |
   |---|---|
   | `laavu.png` | laavu |
   | `kota.png` | kota, kammi |
   | `tupa.png` | tupa |
   | `nuotiopaikka.png` | nuotiopaikka |
   | `keittokatos.png` | keittokatos |
   | `nakotorni.png` | näkötorni |
   | `nakoalapaikka.png` | näköalapaikka |
   | `telttapaikka.png` | telttapaikka |
   | `kaymala.png` | käymälä |
   | `opastuspiste.png` | opastuspiste |
   | `luontokeskus.png` | luontokeskus |
   | `puuvaja.png` | puuvaja |
   | `vesipiste.png` | kaivo / vesipiste |
   | `rantautumispaikka.png` | rantautumispaikka |
   | `pysakointi.png` | pysäköinti |

   Puuttuvat tiedostot korvataan automaattisesti `retkeily/`-sarjan kuvakkeilla.

2. Ota sarja käyttöön ympäristömuuttujalla `LIPAS2TAK_ICONS_DIR=<kansio>`
   (docker-lipas-integrationissa: ks. `.env.example`).

Iconsetin UID pysyy samana sarjasta riippumatta: kun ATAKiin asennetaan uusi
`lipas2tak_iconset.zip`, jo jaetut merkit vaihtavat ulkoasua.
