# Suunnitelma ja päätökset

Päivitetty 7.10.2026.

## Arkkitehtuuri

```
Lipas API ─┐
OSM ───────┼─> python-lipas2tak-tool ──> data/output/ (index.json + tiedostot)
Tilastok. ─┘          (generaattori)              │
                                                  ├─> nginx: KMZ/KML/datapaketit julkisesti (HTTPS)
                                                  └─> feeder(it): Data Sync -missiot TAK Serverille
                                                      (oma kontti per serveri/ryhmä/sertifikaatti)
```

- **python-lipas2tak-tool** (tämä repo): datan haku, käsittely ja tiedostot. Ei tiedä TAK Servereistä mitään.
- **docker-lipas-integration**: compose-pino (generaattori + nginx + feederit).
- **Feederit**: lukevat `index.json`:n ja vievät valitut alueet ja kielet Data Syncin missioihin omalla sertifikaatillaan. Samaa aineistoa voi jakaa useille servereille ja ryhmille.

## Päätökset

| # | Aihe | Päätös |
|---|---|---|
| 1 | Kohdetyypit | laavut, kodat, kammit, tuvat, nuotio- ja keittopaikat, näkötornit ja näköalapaikat, telttapaikat, käymälät, opastuspisteet, luontokeskukset, puuvajat, vesipisteet, rantautumispaikat, pysäköinti; reitit: luontopolut, retkeilyreitit, monikäyttö-, pyöräily- ja melontareitit. **Ei talvireittejä.** |
| 2 | Käymälät | Lipaksen LOI-rajapinta (dry-toilet, wc) + OSM `amenity=toilets` 300 m:n säteellä retkikohteista |
| 3 | Alueet | kansallispuistot → erämaa-alueet → valtion retkeilyalueet |
| 4 | Maakunnat | kaikki ylläpitäjät, vain kohdan 1 tyypit (ei kuntoratoja/lähiliikuntaa) |
| 5 | Pilkkominen | ensin kokonaisuutena; KMZ myös tyyppiryhmittäin; hashtagit remarksissa |
| 6 | Kuvakkeet | väliaikainen sarja; lupa pyydetty Metsähallitukselta (kirjaamo@metsa.fi) |
| 7 | Reittien värit | samankaltaiset reitit samalla värillä (types.yaml) |
| 8 | Reittimuoto | viiva (u-d-f) + GPX; navigoitavat b-m-r myöhemmin (**muistutus**) |
| 10 | Kielet | suomi ja englanti erikseen |
| 11 | Remarks | palvelut + lyhyt kuvaus ≤ 500 merkkiä + linkki + hashtagit |
| 12 | TAK Server | 5.8-84, Data Sync ryhmä-/kanavakohtaisesti |
| 13 | Clientit | pääpaino ATAK 5.8, WinTAK 5.8 |
| 14 | Jakelu | julkinen HTTPS, oma domain |
| 16 | Poistot | poistuneet kohteet poistetaan; viikkotason muutosraportti |
| – | Korkeus | ei kirjoiteta; ATAK sitoo kohteet omaan korkeusmalliinsa |

## ATAK-esimerkin havainnot (Iivaara-datapaketti)

- Mission Package v2: `MANIFEST/manifest.xml` ja `<uid>/<uid>.cot`.
- Reitti `b-m-r`: `point` 0,0, pisteet `<link>`-elementteinä (`b-m-p-w` alussa ja lopussa, `b-m-p-c` välissä), `link_attr` (Walking/On Foot/CP/Ascending Check Points), tyhjä `__routeinfo/__navcues`.
- 10,6 km:n reitissä 421 pistettä ilman harvennusta, eli satojen pisteiden reitit toimivat.
- Väri on etumerkillinen ARGB (`-8454017` = `#7F007F`).
- `remarks` on vapaata tekstiä, ja hashtagit kirjoitetaan siihen sellaisenaan.

## Datahavainnot (Lipas, 7.10.2026)

- Kansallispuistot ovat tyypillä 111. Nuuksio = lipas-id 606198.
- Nuuksiosta Lipaksessa on vain muutama polku (Nahkiaispolku, Päivättärenpolku, Maahisenkierros). Espoosta, Vihdistä ja Kirkkonummelta **ei löytynyt yhtään laavua (301)**, eikä Metsähallituksen pääreittejä (Haukankierros ym.). Luontoon.fi saa nämä Metsähallituksen omista järjestelmistä. Tarkistetaan ensimmäisellä oikealla ajolla.
- LOI-rajapinnassa on käymälöitä (`dry-toilet` ≈ 216 kpl koko maassa), mukana myös testidataa (suodatetaan nimen ja tilan perusteella).
- Tyyppikoodi 205 ei ole käytössä; rantautumispaikat tulevat LOI:sta (`landing-spot`).
- Valtion retkeilyalueiden tyyppikoodi on selvittämättä.

## Testattavaa ATAKissa (MVP)

1. ✅ Iconset (`defaultGroup`/`skipResize`, `Retkeily/*.png`, polku `<uid>/Retkeily/<kuvake>.png`) toimii ATAK 5.8:ssa (7.10.2026).
2. ✅ `u-d-f`-viiva ilman korkeutta toimii; silmukkareitit vaativat `fillColor 0` (muuten täyttö).
3. Hashtag-haku, kun tagit ovat pitkän remarksin lopussa.
4. GPX `<rte>` → ATAK-reitti; siirtyykö `<desc>` remarksiin.
5. KMZ-verkkolinkin päivittyminen ATAKissa ja WinTAKissa.
6. Datapaketin `onReceiveDelete` ja saman paketin UID:n korvautuminen uudella versiolla.

## Seuraavat vaiheet

1. Ensimmäinen oikea ajo palvelimella (`lipas2tak run --dump data/raw`). Raakadata talteen analyysia varten.
2. ATAK-testit yllä olevan listan mukaan.
3. Feeder (Data Sync) docker-lipas-integration-repoon.
4. Erämaat ja valtion retkeilyalueet.
5. Navigoitavat `b-m-r`-reitit valituista reiteistä.
6. Lopulliset kuvakkeet (lupa tai oma sarja).
