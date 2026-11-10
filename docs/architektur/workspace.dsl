/*
 * where2build as a C4 model, in the Structurizr DSL.
 *
 * Identifiers are English like the code; names and descriptions are German
 * because they are what a reader of the diagrams sees. The model mirrors
 * docker-compose.yml, backend/app/main.py and frontend/src -- when one of those
 * changes shape, change this file and run `node scripts/architecture.mjs`,
 * which regenerates workspace.json, the interactive page and the images.
 */
workspace "where2build" "Grundstücks-Check Sachsen: Inserat → amtliche Flurstücke → Bodenrichtwert, Bebauung, Umfeld und Wege." {

    !identifiers hierarchical

    model {
        properties {
            "structurizr.groupSeparator" "/"
        }

        buyer = person "Bauinteressent:in" "Prüft ein Grundstücksinserat: welche Flurstücke, was sie amtlich kosten, welches Haus darauf passt und wie weit es zu Schule, Arbeit und Haltestelle ist."
        recipient = person "Empfänger:in eines Links" "Öffnet ein geteiltes Grundstück ohne Konto – der Token ist der Zugang."
        operator = person "Betreiber:in" "Verwaltet Konten, Freigaben, Caches und Jobs im Verwaltungsbereich. Bootstrap über ADMIN_ACCOUNTS."

        group "Freistaat Sachsen" {
            geosn = softwareSystem "GeoSN Geodienste" "Landesamt für Geobasisinformation: ALKIS-WFS (Flurstücke, Gebäude), WMS für Luftbild, WebAtlas und Liegenschaftskarte, Download der Hauskoordinaten." "Extern,Amtlich"
            boris = softwareSystem "BORIS Sachsen" "Bodenrichtwerte. Kein WFS – nur WMS GetFeatureInfo." "Extern,Amtlich"
            luis = softwareSystem "LUIS Sachsen" "ArcGIS-REST des Landesumweltamts: Lärm, Hochwasser, Schutzgebiete, Boden, Radon." "Extern,Amtlich"
            rapis = softwareSystem "RAPIS Sachsen" "Raumplanungsinformationssystem: Bauleitpläne und Art der Nutzung." "Extern,Amtlich"
        }
        uba = softwareSystem "Umweltbundesamt Luftdaten" "Messstationen und Luftqualität, bundesweit, ohne Schlüssel." "Extern,Amtlich"

        group "Offene Daten und Dienste" {
            openfreemap = softwareSystem "OpenFreeMap" "Vektor-Grundkarte: Style, Kacheln, Glyphen, Sprites." "Extern"
            overpass = softwareSystem "Overpass API" "Live-Abfragen an OpenStreetMap. Optionaler Ersatz für Nachbargebäude und Ziele." "Extern,Optional"
            transitous = softwareSystem "Transitous" "Öffentliche MOTIS-Instanz. Alternative zum eigenen Router (docker-compose.transitous.yml)." "Extern,Optional"
            geofabrik = softwareSystem "Geofabrik" "OSM-Extrakt Sachsen für Router und POI-Index." "Extern"
            gtfs = softwareSystem "DELFI-GTFS" "Deutschlandweiter Fahrplan, bezogen über Transitous." "Extern"
            ecb = softwareSystem "EZB" "Tageskurs für die Umrechnung der Modellpreise." "Extern"
        }

        group "Inserate und Anbieter" {
            portals = softwareSystem "Immobilienportale" "kleinanzeigen.de, immowelt.de u. a. ImmoScout24 nur über das Bookmarklet, weil jede Serveranfrage an der WAF scheitert." "Extern"
            manufacturers = softwareSystem "Hausanbieter-Websites" "Typenhäuser: Maße, Grundfläche, Preis. Abruf nur auf der Domain des Anbieters." "Extern"
        }
        llm = softwareSystem "LLM-Anbieter" "OpenRouter, OpenAI, Anthropic, Ollama oder ein anderer OpenAI-kompatibler Host – Wahl der Installation (LLM_ANBIETER)." "Extern"
        linkbots = softwareSystem "Link-Vorschau-Bots" "Messenger und Chats, die og:-Tags und das Vorschaubild eines geteilten Links lesen." "Extern"

        w2b = softwareSystem "where2build" "Löst ein Inserat in amtliche Flurstücke auf, misst sie, vergleicht den Preis mit dem Bodenrichtwert, platziert ein Typenhaus im Abstandsflächen-Rahmen und berechnet Wege." {

            group "Im Browser" {
                spa = container "Web-App" "Die Oberfläche. Hält alle Geometrie, die angefasst wird: Puffern, Drehen, Kollision laufen beim Ziehen. Speichert lokal, synchronisiert mit Konto." "Vue 3 (Options API), Vite, MapLibre GL, localStorage" "Browser" {
                    group "Ansichten" {
                        views = component "Ansichten und Router" "Startseite, Aufnahme-Assistent, Grundstück, Vergleich, Haustypen, Ziele, Daten, Konto, geteilte Ansicht." "vue-router, views/*.vue"
                        adminViews = component "Verwaltungsoberfläche" "Kennzahlen, Statistik, Konten, Fehler, Freigaben, Betrieb, Prüfprotokoll." "components/admin/*.vue"
                    }
                    group "Eingabe und Suche" {
                        queryBox = component "Suchfeld" "Liest die Eingabe, bevor es nachschlägt: Adresse, Koordinate oder Flurstück – und sagt, wie es gelesen hat." "QueryBox.vue, lib/queryInput.js"
                        handoff = component "Übergabe-Empfänger" "Nimmt die vom Bookmarklet übergebene Seite per postMessage entgegen." "lib/handoff.js, lib/bookmarklet.js"
                        searchClient = component "Suchlauf-Client" "Liest den NDJSON-Strom der Flurstückssuche und lässt die Karte mitwachsen." "lib/search.js, ParcelSearch.vue, EvidenceMap.vue"
                    }
                    group "Grundstück" {
                        sitePlan = component "Lageplan" "Flurstücke, Abstandsflächen-Rahmen nach § 6 SächsBO, Hausplatzierung, Kollision." "SitePlan.vue, lib/geometry.js, lib/projection.js, MapLibre"
                        neighbourhood = component "Nachbarschaft" "Klassifiziert Nachbargebäude und zeichnet 3-m-Schraffur und 6-m-Zone." "lib/neighbourhood*.js, NeighbourhoodPane.vue"
                        findings = component "Befund-Vorlagen" "Feste deutsche Sätze aus strukturierten Daten – kein Modell schreibt UI-Text." "lib/findings.js, lib/siteChecks.js, CheckList.vue"
                        routes = component "Wege und Umfeld" "Reisezeiten, Routen, nächste Ziele." "RouteCards.vue, NearbyPanel.vue, lib/routes.js"
                    }
                    group "Daten" {
                        store = component "Zustand und Speicher" "Reaktiver Zustand, localStorage, Abgleich mit dem Konto." "lib/store.js, lib/serverStore.js"
                        apiClient = component "API-Client" "fetch gegen /api; deutsche detail-Meldungen statt Beispieldaten." "lib/api.js"
                    }
                }
                bookmarklet = container "Bookmarklet" "Läuft auf der Seite des Portals, öffnet die App und übergibt document.outerHTML per postMessage – ohne CORS und am CSP des Portals vorbei." "JavaScript" "Browser"
            }

            group "Stapel (docker compose)" {
                webserver = container "Webserver" "Liefert den Build aus, leitet /api weiter, setzt per SSI die og:-Tags geteilter Links ein." "nginx" "Server"

                api = container "API-Backend" "Proxy und Plattencache vor den Ämtern, Flurstückssuche, Inseratsauswertung, Konten, Freigaben, Verwaltung." "Python, FastAPI, httpx, Shapely" "Server" {
                    group "Amtliche Daten" {
                        parcels = component "Flurstücke" "Adresse, Koordinate, Gemarkung + Nummer oder Kennzeichen → GeoJSON mit amtlicher Fläche; Vereinigung mehrerer Flurstücke; Plausibilitätsprüfung." "routers/parcels.py, services/alkis.py, plausibility.py"
                        landValue = component "Bodenrichtwert" "€/m², Zone, Stichtag, Richtwertgrundstück." "routers/landvalue.py, services/boris.py"
                        siteChecks = component "Standortprüfungen" "Lärm, Hochwasser, Radon, Wasser- und Naturschutz, Hangneigung, Boden, Luft – jede Prüfung mit Daten oder eigenem fehler." "routers/sitechecks.py, services/luis.py, services/airquality.py"
                        planning = component "Planungsrecht" "Bauleitplan und Art der Nutzung am Grundstück." "routers/planning.py, services/rapis.py"
                        neighbours = component "Nachbargebäude" "Gebäudeumrisse aus ALKIS, Overpass als Ersatz." "routers/neighbours.py, services/overpass.py"
                        gemarkungen = component "Gemarkungsverzeichnis" "5 339 Gemarkungen aus einer eingecheckten Datei – der WFS wird nie gefragt." "routers/gemarkungen.py, gemarkung_index.py"
                    }
                    group "Inserat und Suche" {
                        listings = component "Inseratsauswertung" "Portal-Adapter, Feldleser, OCR des Katasterauszugs, Modell als letzter Leser; jeder Modellwert muss das Beleg-Tor passieren." "routers/listings.py, services/portals.py, services/portal_fields.py, services/ocr.py, services/beleg.py, services/befund.py"
                        searchEngine = component "Flurstückssuche" "Treppe statt Pipeline: harte Filter entscheiden, Gewichte ordnen. Antwortet als NDJSON." "routers/search.py, search/engine.py, search/blocks.py, search/indicia.py, search/distance.py, search/ladder.py, search/scoring.py, search/envelope.py"
                        llmClient = component "Modell-Client" "Ein Client je Wire-Format: OpenAI-kompatibel oder Anthropic-Adapter. Prompts als Inhalt, nicht im Router." "services/llm.py, services/prompts.py"
                        lehrbuch = component "Lehrbuch" "Protokoll, wo Muster und Modell sich widersprechen; Telefonnummern und Mailadressen geschwärzt." "routers/lehrbuch.py, services/lehrbuch.py"
                        houseTypes = component "Haustypen" "Typenhaus von der Anbieterseite lesen." "routers/housetypes.py"
                    }
                    group "Wege und Umfeld" {
                        routing = component "Erreichbarkeit und Geocoder" "Reisezeiten und Routen; Geocoding aus amtlichen Hauskoordinaten plus MOTIS." "routers/reachability.py, routers/geocode.py, services/motis.py, address_index.py"
                        nearby = component "Ziele in der Nähe" "Schule, Park, Haltestelle … nach Fußweg; Haltestellen aus dem Fahrplan, Rest aus dem POI-Index." "routers/nearby.py, services/nearby.py, poi_index.py"
                        mapProxy = component "Karten-Proxy" "Rasterkacheln der GeoSN-WMS und der Lärmkarte; Vektor-Grundkarte umgeschrieben, damit MapLibre nie selbst ins Netz geht." "routers/tiles.py, routers/basemap.py, services/tiles.py, services/basemap.py"
                    }
                    group "Konten und Betrieb" {
                        auth = component "Anmeldung (BFF)" "OIDC mit PKCE auf der Serverseite; der Browser bekommt nur ein signiertes HttpOnly-Cookie." "routers/auth.py, services/oidc.py, session.py"
                        storage = component "Kontospeicher" "Ein Dokument je Grundstück; 200 Grundstücke, 2 MiB je Dokument." "routers/storage.py, services/storage.py"
                        shares = component "Freigaben" "Geteilte Momentaufnahme per Token, og:-Kopf und 1200×630-Vorschaubild." "routers/shares.py, services/preview.py, services/sharemeta.py, Pillow"
                        admin = component "Verwaltung" "Kennzahlen, Sperren, Fehlerlog, Freigaben, Caches, Prüfprotokoll, Jobanfragen." "routers/admin.py, services/admin.py, jobs.py, prices.py"
                    }
                    group "Querschnitt" {
                        upstream = component "Upstream und Cache" "Ein Ort für ausgehende Anfragen: TTL-Cache im Speicher und auf Platte, Fehler als deutsche HTTP-Antwort. Liest neu gebaute Indizes und die Preisliste ohne Neustart." "upstream.py, cache.py, errors.py, reloading.py"
                        budget = component "Anfragebudget und Telemetrie" "Gleitendes Budget je Konto bzw. Adresse; Zählung als Stundenaggregate, nie je Anfrage." "ratelimit.py, telemetry.py"
                    }
                }

                db = container "Datenbank" "Konten, Grundstücke, Freigaben, Einstellungen, Abweichungen, Sperren, Nutzungsaggregate, Fehler, Prüfprotokoll, Betriebsansage." "PostgreSQL 16" "Datenbank"
                cache = container "Plattencache" "Antworten der Ämter, Kacheln, Downloads. Verlust kostet Zeit, nicht Richtigkeit." "Docker-Volume" "Datei"
                indexes = container "Lokale Indizes" "POI-Index (OSM) und amtliche Hauskoordinaten; neu gelesen, sobald der Scheduler sie neu gebaut hat." "SQLite/Dateien im Volume" "Datei"
                motis = container "Router" "Multimodales Routing, Haltestellen und Geocoder auf diesem Rechner." "MOTIS 2.11" "Fremdprodukt"
                scheduler = container "Scheduler" "Wiederkehrende Jobs aus ops/jobs.json: Cache-Sweep, Freigaben-Sweep, Indizes, Preisliste. Nimmt „Jetzt starten“ als Datei entgegen." "Python, scripts/run_jobs.py" "Server"
                importer = container "Einmal-Importe" "routing-data, motis-import, indexes: Rohdaten laden, Graph bauen, Indizes anlegen." "Python, MOTIS import" "Server,Einmalig"
                idp = container "Identitätsanbieter" "Anmeldung und Registrierung, Blueprint aus ops/authentik." "authentik 2025.2" "Fremdprodukt"
                idpCache = container "IdP-Cache" "Sitzungen und Aufgabenwarteschlange von authentik." "Redis 7" "Fremdprodukt,Datenbank"
            }
        }

        # --- people ---------------------------------------------------------
        buyer -> w2b.spa "Sucht, prüft, plant" "HTTPS"
        buyer -> w2b.bookmarklet "Klickt auf der Inseratsseite"
        buyer -> portals "Liest Inserate" "HTTPS"
        recipient -> w2b.spa "Öffnet /geteilt/…" "HTTPS"
        operator -> w2b.spa "Verwaltet unter /verwaltung" "HTTPS"
        buyer -> w2b.idp "Meldet sich an, legt Konto an" "HTTPS, Port 9000"
        linkbots -> w2b.webserver "Liest og:-Tags und Vorschaubild" "HTTPS"

        # --- browser side ---------------------------------------------------
        w2b.bookmarklet -> w2b.spa.handoff "Übergibt die Inseratsseite" "postMessage"
        w2b.spa -> w2b.webserver "Lädt App, ruft /api" "HTTPS, JSON/NDJSON"
        w2b.spa.views -> w2b.spa.queryBox "Bettet ein"
        w2b.spa.views -> w2b.spa.sitePlan "Bettet ein"
        w2b.spa.views -> w2b.spa.routes "Bettet ein"
        w2b.spa.views -> w2b.spa.adminViews "Leitet unter /verwaltung weiter"
        w2b.spa.queryBox -> w2b.spa.searchClient "Startet Suchlauf"
        w2b.spa.handoff -> w2b.spa.searchClient "Reicht Inserat weiter"
        w2b.spa.sitePlan -> w2b.spa.neighbourhood "Zeichnet Nachbarschaft"
        w2b.spa.sitePlan -> w2b.spa.findings "Formuliert Befunde"
        w2b.spa.neighbourhood -> w2b.spa.findings "Formuliert Befunde"
        w2b.spa.searchClient -> w2b.spa.store "Legt Grundstück an"
        w2b.spa.sitePlan -> w2b.spa.store "Liest und schreibt Platzierung"
        w2b.spa.routes -> w2b.spa.store "Liest Ziele"
        w2b.spa.store -> w2b.spa.apiClient "Synchronisiert Konto"
        w2b.spa.searchClient -> w2b.spa.apiClient "Ruft Suche und Auswertung"
        w2b.spa.queryBox -> w2b.spa.apiClient "Fragt Geocoder und Gemarkungen"
        w2b.spa.sitePlan -> w2b.spa.apiClient "Lädt Flurstücke, Nachbarn, Kacheln"
        w2b.spa.findings -> w2b.spa.apiClient "Lädt Bodenrichtwert, Prüfungen, Planung"
        w2b.spa.routes -> w2b.spa.apiClient "Lädt Wege und Ziele"
        w2b.spa.adminViews -> w2b.spa.apiClient "Ruft /api/verwaltung"
        w2b.spa.apiClient -> w2b.webserver "Ruft /api" "HTTPS, JSON/NDJSON"

        # --- web server -----------------------------------------------------
        w2b.webserver -> w2b.api "Leitet /api weiter" "HTTP, X-Forwarded-For"
        w2b.webserver -> w2b.api.shares "Holt og:-Kopf für /geteilt/…" "SSI-Subrequest"
        w2b.webserver -> w2b.api.parcels "/api/parcels/resolve, nearby, streets" "HTTP"
        w2b.webserver -> w2b.api.searchEngine "/api/parcels/search" "HTTP, NDJSON"
        w2b.webserver -> w2b.api.listings "/api/listings/extract" "HTTP"
        w2b.webserver -> w2b.api.houseTypes "/api/housetypes/extract" "HTTP"
        w2b.webserver -> w2b.api.landValue "/api/landvalue" "HTTP"
        w2b.webserver -> w2b.api.siteChecks "/api/site-checks" "HTTP"
        w2b.webserver -> w2b.api.planning "/api/planning" "HTTP"
        w2b.webserver -> w2b.api.neighbours "/api/neighbours" "HTTP"
        w2b.webserver -> w2b.api.gemarkungen "/api/gemarkungen" "HTTP"
        w2b.webserver -> w2b.api.routing "/api/reachability, /api/geocode" "HTTP"
        w2b.webserver -> w2b.api.nearby "/api/nearby" "HTTP"
        w2b.webserver -> w2b.api.mapProxy "/api/tiles, /api/basemap" "HTTP"
        w2b.webserver -> w2b.api.auth "/api/auth" "HTTP"
        w2b.webserver -> w2b.api.storage "/api/plots, /api/settings, /api/account" "HTTP"
        w2b.webserver -> w2b.api.admin "/api/verwaltung" "HTTP"
        w2b.webserver -> w2b.api.lehrbuch "/api/lehrbuch" "HTTP"

        # --- inside the API -------------------------------------------------
        w2b.api.searchEngine -> w2b.api.parcels "Fragt ALKIS in engen Fragen"
        w2b.api.searchEngine -> w2b.api.routing "Verortet Straßen und Orte"
        w2b.api.listings -> w2b.api.llmClient "Lässt das Modell als letzten Leser lesen"
        w2b.api.listings -> w2b.api.lehrbuch "Schreibt Abweichungen"
        w2b.api.houseTypes -> w2b.api.llmClient "Extrahiert Typenhaus"
        w2b.api.nearby -> w2b.api.routing "Haltestellen und Linien"
        w2b.api.neighbours -> w2b.api.parcels "Gebäude aus ALKIS"
        w2b.api.parcels -> w2b.api.upstream "Anfragen mit Cache"
        w2b.api.landValue -> w2b.api.upstream "Anfragen mit Cache"
        w2b.api.siteChecks -> w2b.api.upstream "Anfragen mit Cache"
        w2b.api.mapProxy -> w2b.api.upstream "Kacheln mit Cache"
        w2b.api.auth -> w2b.api.budget "Liefert Konto für das Budget"
        w2b.api.storage -> w2b.api.auth "Prüft Sitzung"
        w2b.api.shares -> w2b.api.storage "Liest Grundstück"
        w2b.api.admin -> w2b.api.auth "Prüft Administrator"

        # --- API to data and services in the stack -------------------------
        w2b.api.storage -> w2b.db "Liest und schreibt Grundstücke" "SQL"
        w2b.api.shares -> w2b.db "Liest und schreibt Freigaben" "SQL"
        w2b.api.admin -> w2b.db "Kennzahlen, Sperren, Prüfprotokoll" "SQL"
        w2b.api.lehrbuch -> w2b.db "Schreibt Abweichungen" "SQL"
        w2b.api.budget -> w2b.db "Schreibt Stundenaggregate" "SQL"
        w2b.api.upstream -> w2b.cache "Liest und schreibt Antworten" "Dateisystem"
        w2b.api.admin -> w2b.cache "Leert Caches" "Dateisystem"
        w2b.api.admin -> w2b.scheduler "Legt Jobanfrage ab" "Datei im State-Volume"
        w2b.api.routing -> w2b.indexes "Liest Hauskoordinaten" "Datei"
        w2b.api.nearby -> w2b.indexes "Liest POI-Index" "Datei"
        w2b.api.routing -> w2b.motis "Routen und Geocoding" "HTTP, JSON"
        w2b.api.auth -> w2b.idp "Authorization Code + PKCE, Token-Tausch" "OIDC"
        w2b.idp -> w2b.db "Eigene Datenbank „authentik“" "SQL"
        w2b.idp -> w2b.idpCache "Sitzungen, Aufgaben" "Redis"
        w2b.scheduler -> w2b.cache "Sweep" "Dateisystem"
        w2b.scheduler -> w2b.indexes "Baut Indizes neu" "Datei"
        w2b.scheduler -> w2b.db "Räumt abgelaufene Freigaben" "SQL"
        w2b.importer -> w2b.indexes "Legt Indizes an" "Datei"
        w2b.importer -> w2b.motis "Baut den Routing-Graphen" "Volume motis-graph"

        # --- API to the outside world --------------------------------------
        w2b.api.parcels -> geosn "Flurstücke per Punkt, Kennzeichen, Gemarkung" "WFS 2.0, GML"
        w2b.api.neighbours -> overpass "Gebäude als Ersatz" "Overpass QL"
        w2b.api.landValue -> boris "GetFeatureInfo" "WMS"
        w2b.api.siteChecks -> luis "Lärm, Wasser, Natur, Boden, Radon" "ArcGIS REST"
        w2b.api.siteChecks -> uba "Luftqualität" "REST, JSON"
        w2b.api.planning -> rapis "Bauleitplanung" "ArcGIS REST"
        w2b.api.mapProxy -> geosn "Luftbild, WebAtlas, Liegenschaftskarte" "WMS"
        w2b.api.mapProxy -> luis "Lärmkarte" "ArcGIS export"
        w2b.api.mapProxy -> openfreemap "Style, Vektorkacheln, Glyphen" "HTTPS"
        w2b.api.listings -> portals "Lädt Inseratsseite" "HTTPS"
        w2b.api.houseTypes -> manufacturers "Lädt Typenhausseite" "HTTPS"
        w2b.api.llmClient -> llm "Strukturierte Extraktion" "HTTPS, JSON"
        w2b.api.routing -> transitous "Routen, wenn kein eigener Router läuft" "HTTP, JSON"
        w2b.scheduler -> geosn "Hauskoordinaten (vierteljährlich)" "HTTPS"
        w2b.scheduler -> geofabrik "OSM-Extrakt für den POI-Index" "HTTPS"
        w2b.scheduler -> llm "Modellpreise" "HTTPS"
        w2b.scheduler -> ecb "Referenzkurs" "HTTPS, XML"
        w2b.importer -> geofabrik "OSM-Extrakt Sachsen" "HTTPS"
        w2b.importer -> gtfs "Fahrplan" "HTTPS, GTFS"
        w2b.importer -> geosn "Hauskoordinaten" "HTTPS"

        # --- deployment -----------------------------------------------------
        local = deploymentEnvironment "Lokaler Stapel" {
            deploymentNode "Endgerät" "Rechner oder Telefon der Nutzer:in" "" {
                deploymentNode "Browser" "" "Chromium, Firefox, Safari" {
                    containerInstance w2b.spa
                    containerInstance w2b.bookmarklet
                }
            }
            deploymentNode "Docker-Host" "Ein Rechner mit docker compose; Projektname where2build" "Docker Compose" {
                deploymentNode "frontend" "Port 8080 → 80" "nginx:alpine" {
                    containerInstance w2b.webserver
                }
                deploymentNode "backend" "Healthcheck /api/health" "python:slim" {
                    containerInstance w2b.api
                }
                deploymentNode "scheduler" "" "python:slim" {
                    containerInstance w2b.scheduler
                }
                deploymentNode "routing-data, motis-import, indexes" "Laufen einmal und beenden sich" "python:slim, motis" {
                    containerInstance w2b.importer
                }
                deploymentNode "motis" "Erster Import ~7 min, 5,6 GiB Spitze" "ghcr.io/motis-project/motis:2.11.2" {
                    containerInstance w2b.motis
                }
                deploymentNode "db, authentik-db-init" "authentik-db-init legt einmal die Datenbank „authentik“ an" "postgres:16-alpine" {
                    containerInstance w2b.db
                }
                deploymentNode "authentik, authentik-worker" "Port 9000" "ghcr.io/goauthentik/server:2025.2.3" {
                    containerInstance w2b.idp
                }
                deploymentNode "authentik-cache" "" "redis:7-alpine" {
                    containerInstance w2b.idpCache
                }
                deploymentNode "Volumes" "backend-cache, indexes, scheduler-state, motis-graph, routing-input, db-data" "Docker-Volumes" {
                    containerInstance w2b.cache
                    containerInstance w2b.indexes
                }
            }
            deploymentNode "Internet" "" "" {
                softwareSystemInstance geosn
                softwareSystemInstance boris
                softwareSystemInstance luis
                softwareSystemInstance rapis
                softwareSystemInstance uba
                softwareSystemInstance openfreemap
                softwareSystemInstance llm
                softwareSystemInstance portals
            }
        }
    }

    views {
        systemContext w2b "Kontext" "Wer where2build benutzt und welche Dienste es fragt." {
            include *
            exclude geofabrik gtfs ecb
            autoLayout lr
        }

        container w2b "Container" "Was im Browser läuft, was im Stapel läuft, und die Dienste dahinter." {
            include *
            exclude buyer->portals
            autoLayout lr
        }

        component w2b.api "Backend" "Die Bausteine des API-Backends, nach Aufgaben gruppiert." {
            include *
            exclude w2b.webserver->w2b.api.shares
            # What the siblings say to each other belongs to the container view.
            exclude "w2b.idp -> *" "w2b.scheduler -> *" "w2b.importer -> *"
            autoLayout lr
        }

        component w2b.spa "WebApp" "Die Bausteine der Web-App, nach Aufgaben gruppiert." {
            include *
            autoLayout lr
        }

        dynamic w2b "InseratZuFlurstueck" "Ein Inserat wird übergeben, gelesen und zum amtlichen Flurstück aufgelöst." {
            buyer -> w2b.bookmarklet "Klickt auf der Inseratsseite"
            w2b.bookmarklet -> w2b.spa "Übergibt document.outerHTML per postMessage"
            w2b.spa -> w2b.webserver "POST /api/listings/extract"
            w2b.webserver -> w2b.api "Leitet weiter"
            w2b.api -> llm "Liest, was die Muster nicht fanden (optional)"
            w2b.spa -> w2b.webserver "POST /api/parcels/search"
            w2b.webserver -> w2b.api "Leitet weiter, NDJSON-Strom zurück"
            w2b.api -> geosn "Flurstücke per Gemarkung und Nummer, sonst Flächentreppe"
            w2b.api -> w2b.motis "Verortet Straße oder Ort"
            w2b.spa -> w2b.webserver "GET /api/landvalue, POST /api/site-checks"
            w2b.webserver -> w2b.api "Leitet weiter"
            w2b.api -> boris "Bodenrichtwert"
            autoLayout lr
        }

        deployment w2b local "Verteilung" "docker compose auf einem Rechner: welcher Dienst in welchem Container läuft." {
            include *
            autoLayout lr
        }

        styles {
            # The palette of frontend/src/styles/tokens.css: Loden for what is
            # ours, darker the higher the level; ochre for the authorities.
            element "Element" {
                color #ffffff
                fontSize 22
            }
            element "Person" {
                shape Person
                background #1c2e23
            }
            element "Software System" {
                background #2f4a3a
            }
            element "Container" {
                background #456b52
            }
            element "Component" {
                background #9db39a
                color #1e1a16
            }
            element "Extern" {
                background #6f675c
            }
            element "Amtlich" {
                background #7c5620
            }
            element "Optional" {
                border dashed
            }
            element "Browser" {
                shape WebBrowser
            }
            element "Datenbank" {
                shape Cylinder
            }
            element "Datei" {
                shape Folder
            }
            element "Fremdprodukt" {
                background #5c6f62
            }
            element "Einmalig" {
                border dashed
            }
            relationship "Relationship" {
                color #6f675c
            }
        }
    }
}
