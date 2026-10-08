# python-lipas2tak-tool

Hakee retkeilykohteet ja reitit [Lipaksesta](https://lipas.fi) (sekä täydentävästi OpenStreetMapista) ja tuottaa niistä TAK-käyttöön sopivat tiedostot. Tiedostot tehdään sekä kansallispuisto- että maakuntakohtaisesti, suomeksi ja englanniksi.

| Tuotos | Käyttö |
|---|---|
| Datapaketti `*.zip` (CoT-merkit + reittiviivat) | ATAK/WinTAK ilman serveriä tai Data Sync -feederin lähteenä |
| `*.kmz` (kaikki kohteet, kansio per tyyppi) | tuonti tai KML-verkkolinkin kohde |
| `*_<ryhmä>.kmz` | tyyppikohtaiset tasot (laavut/kodat/tuvat, nuotiopaikat, näkötornit …) |
| `*.kml` (NetworkLink) | päivittyvä linkki KMZ-tiedostoon |
| `*_gpx.zip` (`<rte>`) | reitit, jotka ATAK muuntaa navigoitaviksi |
| `iconset/lipas2tak_iconset.zip` | kuvakesarja, asennetaan kerran |
| `index.json` / `index.html` | tuotosluettelo feedereille ja ihmisille |

Merkkien `remarks`-kentässä on kuvaus, palvelut ja hashtagit (`#laavu #nuuksio #uusimaa`), joilla näkymää voi rajata ATAKissa. Reittien remarksissa on pituus, maastomerkintä, esteettömyys ja kuvaus.

Ajastus, tiedostojen jakelu (nginx) ja TAK Server -feederit ovat repossa **docker-lipas-integration**.

## Käyttö

```bash
pip install -e .
lipas2tak run                      # hae kaikki ja tuota data/output/
lipas2tak run --only nuuksio       # vain yksi alue (slug tai avain kansallispuistot/nuuksio)
lipas2tak fetch --dump data/raw    # tallenna raakadata
lipas2tak build --raw data/raw     # tuota tallennetusta datasta ilman verkkoa
lipas2tak schedule --every-days 7  # konttikäyttö: ajo heti ja sitten viikoittain
```

Docker:

```bash
docker build -t lipas2tak .
docker run --rm -v "$PWD/data:/data" -e LIPAS2TAK_PUBLIC_BASE_URL=https://example.org/lipas2tak lipas2tak run
```

### Asetukset

- `config/config.yaml`: lähteet, alueet, tuotokset, URL. Ympäristömuuttujat: `LIPAS2TAK_PUBLIC_BASE_URL`, `LIPAS2TAK_OUTPUT_DIR`, `LIPAS2TAK_CACHE_DIR`, `LIPAS2TAK_ICONS_DIR`, `LIPAS2TAK_OVERPASS_URL`, `LIPAS2TAK_CONFIG`, `LIPAS2TAK_TYPES`.
- `config/types.yaml`: kohdetyypit (Lipas-tyyppikoodit, LOI-tyypit, OSM-tagit), kuvakkeet, värit ja hashtagit. Uuden tyypin lisääminen ei vaadi koodimuutoksia.
- `config/area_names.yaml`: alueiden perusmuotoiset nimet (esim. "Nuuksion" → "Nuuksio").

### Tulosteen rakenne

```
data/output/
  index.json, index.html
  iconset/lipas2tak_iconset.zip
  fi|en/kansallispuistot|maakunnat/<slug>/
    <slug>_<kieli>.zip            datapaketti
    <slug>_<kieli>.kmz / .kml      kaikki + verkkolinkki
    <slug>_<kieli>_<ryhmä>.kmz/.kml
    <slug>_<kieli>_gpx.zip
```

Tiedostot kirjoitetaan ensin väliaikaiseen hakemistoon ja vaihdetaan paikalleen kerralla, joten Lipaksesta poistuneet kohteet katoavat automaattisesti. Muutokset edelliseen ajoon kirjataan tiedostoon `data/cache/changes.jsonl`.

## Tietolähteet

| Lähde | Mitä | Lisenssi |
|---|---|---|
| Lipas REST API v2 `/sports-sites` | laavut, kodat, tuvat, nuotiopaikat, tornit, telttailu, opastuspisteet, reitit, kansallispuistojen rajat | Lipas / JYU, tarkista lähdemerkintä |
| Lipas `/lois` | käymälät, puuvajat, kaivot, näköalapaikat ym. | sama |
| OpenStreetMap (Overpass) | käymälät retkikohteiden lähellä | © OpenStreetMap contributors, ODbL |
| Tilastokeskus WFS | maakuntarajat | CC BY 4.0 |

## Tunnetut rajoitukset ja testattavat asiat

Ks. [docs/suunnitelma.md](docs/suunnitelma.md).

- Kuvakkeet (`icons/retkeily`, piirretty `scripts/make_icons.py`:llä) ovat omia kuvasymboleja retkeilykarttojen tyyliin, eivät Metsähallituksen symboleja. Metsähallitukselta on pyydetty lupaa heidän symboliensa käyttöön; vaihto = uudet PNG:t samoilla nimillä.
- Metsähallituksen ylläpitämiä kohteita ja reittejä puuttuu Lipaksesta paikoin, esim. Nuuksiosta.
- ATAKissa testattavat: iconsetin polkurakenne, `u-d-f`-linkkipisteet ilman korkeutta, hashtag-haku pitkässä remarksissa, GPX `<rte>` → reitti.
