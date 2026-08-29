# OpenRouter-API — Recherche zu `web_fetch`, Structured Outputs und dem ImmoScout-Entscheidungsexperiment

Stand: 29.08.2026. Getestet mit einem OpenRouter-Key mit $2 Startguthaben (siehe „Verbrauchtes Budget" unten).
Quelle für Doku-Aussagen: openrouter.ai/docs (Server-Tools-Guides, API-Referenz), openrouter.ai/blog. Quelle für Live-Verhalten: eigene Aufrufe gegen `https://openrouter.ai/api/v1/chat/completions`.

## 1. Zusammenfassung / Empfehlung

`openrouter:web_fetch` ist ein serverseitiges Tool (kein Client-Roundtrip), das mit korrekter Syntax funktioniert und für harmlose Domains (z. B. Fertighaus-Herstellerseiten) zuverlässig Text liefert — die im Vorprojekt-Dokument skizzierte Architektur ist grundsätzlich tragfähig. Das Entscheidungsexperiment bestätigt exakt das, was in `vorprojekt-anforderungen.html` bereits notiert war: ImmoScout24 blockiert jeden Serverabruf (401, AWS-WAF-Challenge) — auch über alle drei OpenRouter-Fetch-Engines hinweg —, während Kleinanzeigen.de anstandslos HTTP 200 inklusive `og:latitude`/`og:longitude` liefert. Der größte neue Befund dieser Recherche betrifft **nicht** das Fetching, sondern die Kombination aus `tools` **und** `response_format: json_schema, strict:true` in einem einzigen Call: In allen drei getesteten Modellen (gpt-4o-mini, claude-haiku-4.5, gemini-2.5-flash-lite) wurde das angeforderte Schema **nicht** eingehalten — die Modelle lieferten frei erfundene Feldnamen statt des vorgegebenen `Haustyp`-Schemas, obwohl der Fachwert selbst (bebaute Fläche 96,88 m² statt Wohnfläche 159,21 m²) korrekt erkannt wurde. Empfehlung: `/housetypes/extract` und `/listings/extract` als **zwei Calls** bauen — Call 1 nur mit `tools: [web_fetch]` und freiem Text, Call 2 ohne Tools, nur `response_format` auf den bereits geholten Text —, nicht als der eine kombinierte Call, der im Architektur-Codeblock des Vorprojekt-Dokuments skizziert ist.

## 2. Web Fetch — exakte Syntax

`openrouter:web_fetch` ist eines von mittlerweile 12 dokumentierten „Server Tools" (`openrouter:web_search`, `openrouter:datetime`, `openrouter:image_generation`, `openrouter:web_fetch`, `openrouter:apply_patch`, `openrouter:shell`, `openrouter:bash`, `openrouter:fusion`, `openrouter:advisor`, `openrouter:subagent`, `openrouter:experimental__search_models`, `openrouter:tool_search`). Diese sind von den alten, jetzt veralteten Konstrukten zu unterscheiden:

- **Veraltet**: `"plugins": [{"id": "web"}]` und das `:online`-Modell-Suffix (z. B. `"openai/gpt-5.2:online"`) — erzwingt eine einmalige Suche vor der Antwort.
- **Aktuell**: `tools: [{"type": "openrouter:web_search"}]` bzw. `tools: [{"type": "openrouter:web_fetch"}]` — das Modell entscheidet selbst, ob und wie oft es sucht/holt (mehrere Aufrufe pro Konversation möglich).

### Tool-Definition

```json
{
  "type": "openrouter:web_fetch",
  "parameters": {
    "engine": "auto",
    "max_uses": 10,
    "max_content_tokens": 100000,
    "allowed_domains": ["example.com"],
    "blocked_domains": ["blocked.com"]
  }
}
```

| Parameter | Typ | Werte | Bedeutung |
|---|---|---|---|
| `engine` | string | `auto` (Default), `native`, `exa`, `openrouter`, `firecrawl`, `parallel` | Fetch-Backend. `auto` = natives Tool des Providers, sonst Fallback auf Exa. |
| `max_uses` | integer | frei | Maximale Anzahl Fetches pro Chat-Completion-Aufruf. |
| `max_content_tokens` | integer | frei | Content wird bei Überschreitung gekürzt (kein Fehler). |
| `allowed_domains` | string[] | Domainliste | Nur diese Domains dürfen gefetcht werden — zentral für den Herstellerseiten-Case (`allowed_domains: ["elkhaus.de"]`). |
| `blocked_domains` | string[] | Domainliste | Diese Domains werden geblockt. |

**Wichtig laut Vorprojekt-Doku und eigener Bestätigung**: Nur bei `engine: openrouter|exa|parallel` verhält sich `allowed_domains`/`blocked_domains` über alle Modelle gleich; `native` und teilweise `firecrawl` weichen ab.

### Antwortformat des Tools (aus OpenRouter-Doku)

```json
// Erfolg
{
  "url": "https://example.com/article",
  "title": "Article Title",
  "content": "Die Seiteninhalte als Text...",
  "status": "completed",
  "retrieved_at": "2025-07-15T14:30:00.000Z"
}

// Fehler — kommt als Tool-Ergebnis zurück, NICHT als HTTP-Fehler
{
  "url": "https://example.com/404",
  "status": "failed",
  "error": "HTTP 404: Page not found"
}
```

**Das ist ein zentraler Punkt für ImmoScout24**: Die äußere `chat/completions`-Antwort kommt mit HTTP 200, auch wenn der Fetch intern scheitert (401/Challenge). Der Fehler steckt im Tool-Ergebnis, das an das Modell zurückgereicht wird — nicht im HTTP-Status des OpenRouter-Aufrufs selbst. Ein Adapter darf sich also nie auf den äußeren Status verlassen, sondern muss den Modelltext/die Tool-Nutzung auswerten.

**Kein separates Response-Feld für den Tool-Aufruf sichtbar**: In allen eigenen Tests (non-streaming) enthielt die finale `message` nur den Fließtext der Modellantwort, keine `tool_calls`- oder `annotations`/`url_citation`-Liste für `web_fetch`. Lediglich `usage.server_tool_use_details: {tool_calls_requested, tool_calls_executed}` zeigt, dass überhaupt gefetcht wurde. Wer die geholte Roh-URL/den Titel programmatisch braucht, sollte das Modell explizit per Prompt zur Ausgabe von `quelle_url` zwingen (wie im `Haustyp`/`Inserat`-Schema vorgesehen) statt sich auf strukturierte Tool-Metadaten zu verlassen.

### Limits

- `native`/`openrouter`-Engine: **hartes Limit von 50 Fetches pro Request**.
- Serverweit: `max_tool_calls` Default 30, Maximum 30 (gilt für alle Server-Tools zusammen, nicht nur `web_fetch`).

## 3. Web Search (Fallback-Ebene, laut Spec nur bei leeren Links)

```json
{
  "model": "openai/gpt-5.2",
  "tools": [
    {
      "type": "openrouter:web_search",
      "parameters": {
        "engine": "auto",
        "max_results": 5,
        "search_context_size": "high",
        "allowed_domains": ["example.com"],
        "excluded_domains": ["reddit.com"],
        "max_total_results": 20
      }
    }
  ]
}
```

- Engines: `auto` (native oder Exa), `native` (OpenAI/Anthropic/Google/xAI/Perplexity-eigene Suche), `exa`, `parallel`, `firecrawl`.
- Suchergebnisse kommen laut Doku als `annotations` mit `url_citation` (url, title, content-excerpt, start/end index) — im Chat-Completions-Standardformat.

## 4. Preise pro Engine (Stand 29.08.2026, aus Doku — nicht live abgerechnet außer web_fetch/openrouter)

| Feature | Engine | Preis |
|---|---|---|
| **web_fetch** | `openrouter` / `native` | kostenlos (OpenRouter-eigene Infrastruktur) bzw. Provider-Passthrough |
| **web_fetch** | `exa` | **$0,001 pro Fetch** ($1 / 1000 Fetches) |
| **web_fetch** | `parallel` | **$0,001 pro Fetch** |
| **web_fetch** | `firecrawl` | BYOK, eigene Firecrawl-Credits (2+5 Credits/Ergebnis), nicht über OpenRouter abgerechnet |
| **web_search** | `exa` | $0,005/Anfrage (bis 10 Ergebnisse), danach $0,001/Ergebnis |
| **web_search** | `parallel` | analog zu Exa |
| **web_search** | `native` | Provider-Passthrough (z. B. Perplexity $0,005/Anfrage laut älterer Doku-Version) |

**Fallstrick**: Zwei verschiedene Doku-Seiten nennen für Exa-Websuche unterschiedliche Zahlen ($0,005 vs. $0,007 in einer älteren Version) — Preise ändern sich, vor dem Go-Live per `GET /api/v1/models` oder Rechnungsdaten (`usage.cost` im Response) live nachrechnen, nicht die hier notierten Zahlen fest einprogrammieren. Zusätzlich zur Fetch-/Search-Gebühr fallen immer die normalen Token-Kosten des gewählten Modells an — bei einer Herstellerseite mit vielen Tokens (siehe unten: 10.713 Prompt-Tokens für eine einzige ELK-Seite) dominieren die Modell-Tokenkosten, nicht die Fetch-Gebühr.

## 5. Structured Outputs (`response_format: json_schema`, `strict: true`)

### Syntax

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "haustyp",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": { "...": "..." },
        "required": ["...alle Properties..."],
        "additionalProperties": false
      }
    }
  }
}
```

- Modelle mit dokumentiertem `structured_outputs`-Support (per `GET /api/v1/models`, Feld `supported_parameters`) u. a.: `openai/gpt-4o-mini`, `openai/gpt-4.1-mini`, `openai/gpt-5-mini`, `anthropic/claude-haiku-4.5`, `google/gemini-2.5-flash`, `google/gemini-2.5-flash-lite`, `google/gemini-3.x-*`, `minimax/minimax-m2.5`, u. v. a. — **`anthropic/claude-3-haiku` und `google/gemini-2.5-flash-image` unterstützen es laut Modellliste NICHT**.
- Im `strict`-Modus müssen laut Doku **alle** Properties in `required` stehen; optionale Felder werden über `"type": ["number", "null"]` statt echtem Optional-Sein abgebildet (klassisches OpenAI-Strict-Schema-Pattern).

### Live-Befund — die eigentlich wichtige Erkenntnis dieser Recherche

Mit dem exakten `Haustyp`-Schema aus dem Vorprojekt-Dokument UND `tools: [openrouter:web_fetch]` im selben Call getestet (URL: `https://www.elkhaus.de/einfamilienhaus/all-in-one-159/`, `allowed_domains: ["elkhaus.de"]`):

| Modell | `structured_outputs` laut Modellliste | Schema eingehalten? | `bebaute_flaeche_m2` korrekt? |
|---|---|---|---|
| `openai/gpt-4o-mini` | ja | **Nein** — eigene Feldnamen (`haus_typ.bebaute_flaeche_m2`, `netto_raumflaeche_m2`, verschachtelt) statt der vorgegebenen 14 Top-Level-Felder | Ja, 96,88 |
| `anthropic/claude-haiku-4.5` | ja | **Nein** — wieder eigene Feldnamen (`wohnflaeche_m2`, `price_eur`, `roof_types`), zusätzlich Fließtext vor dem JSON-Block | Ja, 96,88 |
| `google/gemini-2.5-flash-lite` | ja | Tool wurde gar nicht erst aufgerufen — Modell antwortete, es könne „nicht garantieren", dass `bebaute_flaeche_m2` die richtige Fläche meint, und verweigerte die Extraktion | n/a |

Beide Modelle, die überhaupt fetchten, haben den **fachlichen** Unterschied Wohnfläche/bebaute Fläche richtig verstanden (96,88 m² statt 159,21 m²) — das bestätigt den im Vorprojekt-Dokument beschriebenen Stolperstein und zeigt, dass er mit einem guten Prompt lösbar ist. Aber **keines** der drei Modelle hat `response_format`/`strict:true` tatsächlich durchgesetzt, sobald gleichzeitig ein Server-Tool im Spiel war. Die OpenAI-/OpenRouter-Doku warnt zwar allgemein „strict modes may restrict which JSON Schema features you can use", macht aber keine Aussage zur Kombination mit Tools — das ist also eine undokumentierte Einschränkung, die empirisch auffiel.

**Konsequenz für die Implementierung**: Der im Vorprojekt-Dokument skizzierte kombinierte Aufruf

```python
await client.chat.completions.create(
    model=s.model,
    messages=[...],
    tools=[{"type": "openrouter:web_fetch", "parameters": {...}}],
    response_format={"type": "json_schema", "json_schema": {...}},
)
```

sollte **nicht** unverändert übernommen werden. Stattdessen zwei Calls:

```python
# Call 1: nur fetchen, freier Text
r1 = await client.chat.completions.create(
    model=s.model,
    messages=[{"role": "user", "content": f"Fetch {url} and return the full relevant page text about the house type, unabridged."}],
    tools=[{"type": "openrouter:web_fetch",
            "parameters": {"engine": s.fetch_engine, "max_content_tokens": 50000,
                           "allowed_domains": [domain_of(url)]}}],
)
raw_text = r1.choices[0].message.content

# Call 2: nur strukturieren, kein Tool im Spiel
r2 = await client.chat.completions.create(
    model=s.model,
    messages=[{"role": "user", "content": f"Extract the Haustyp fields from this text:\n\n{raw_text}"}],
    response_format={"type": "json_schema",
                      "json_schema": {"name": "haustyp", "strict": True,
                                      "schema": Haustyp.model_json_schema()}},
)
haustyp = Haustyp.model_validate_json(r2.choices[0].message.content)
```

Das kostet zwei Roundtrips statt einem, ist dafür aber tatsächlich schemakonform validierbar — im aktuellen Setup wäre `Haustyp.model_validate_json(...)` auf die Antworten aus Call 1 (Freitext mit Fließkommentar) schlicht fehlgeschlagen.

## 6. Live-Test-Beispiele (copy-paste-fähig)

### 6a. Minimaler `web_fetch`-Call (verifiziert, HTTP 200)

**JSON-Request:**
```json
{
  "model": "openai/gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Fetch https://example.com using the web fetch tool and tell me in one sentence what the page says."}
  ],
  "tools": [
    {"type": "openrouter:web_fetch", "parameters": {"engine": "openrouter", "max_content_tokens": 2000}}
  ],
  "max_tokens": 200
}
```

**Antwort (gekürzt):**
```json
{
  "choices": [{"message": {"role": "assistant",
    "content": "The page says that \"This domain is for use in documentation examples without needing permission. Avoid use in operations.\""}}],
  "usage": {
    "prompt_tokens": 410, "completion_tokens": 42, "total_tokens": 452,
    "cost": 0.0000867,
    "server_tool_use_details": {"tool_calls_requested": 1, "tool_calls_executed": 1}
  }
}
```

**Python (AsyncOpenAI, OpenAI-kompatibel):**
```python
from openai import AsyncOpenAI

client = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

resp = await client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "Fetch https://example.com and summarize it in one sentence."}],
    tools=[{"type": "openrouter:web_fetch",
            "parameters": {"engine": "openrouter", "max_content_tokens": 2000}}],
    max_tokens=200,
)
print(resp.choices[0].message.content)
print(resp.usage.cost)  # extra Feld, das OpenRouter an usage anhängt
```

### 6b. `curl`-Einzeiler für schnelle Tests

```bash
curl -sS https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o-mini",
    "messages": [{"role":"user","content":"Fetch https://example.com and summarize it."}],
    "tools": [{"type":"openrouter:web_fetch","parameters":{"engine":"openrouter"}}]
  }'
```

## 7. Entscheidungsexperiment: Kommt ein Serverabruf an ImmoScout24 vorbei?

**Frage laut Vorprojekt-Dokument**: Kommt ein Serverabruf an immobilienscout24.de vorbei, und wenn ja, womit? Getestete Exposé-URL: `https://www.immobilienscout24.de/expose/110185322`. Getestete Kleinanzeigen-URL: `https://www.kleinanzeigen.de/s-anzeige/-wohnbaugrundstueck-fuer-efh-mit-b-plan-688-m-/3425157266-207-4059`.

| Datum | Methode | Ziel | Statuscode | Inhalt vorhanden? | Bemerkung |
|---|---|---|---|---|---|
| 29.08.2026 | `curl`, realistischer Chrome-UA, kostenlos | ImmoScout24 Exposé | **401** | Nein | Antwort ist die AWS-WAF-Seite „Ich bin kein Roboter — ImmobilienScout24" mit `challenge.js` von `*.edge.sdk.awswaf.com` |
| 29.08.2026 | `curl`, realistischer Chrome-UA, kostenlos | Kleinanzeigen-Suchseite (Sachsen, Baugrundstück) | **200** | Ja | 459 KB HTML, enthält u. a. 10+ echte `/s-anzeige/...`-Links |
| 29.08.2026 | `curl`, realistischer Chrome-UA, kostenlos | Kleinanzeigen Einzelanzeige | **200** | Ja | `og:latitude="51.39235087498254"`, `og:longitude="13.3868408203125"` beide vorhanden — Geocoding entfällt |
| 29.08.2026 | OpenRouter `web_fetch`, `engine: openrouter`, Modell `gpt-4o-mini` | ImmoScout24 Exposé | äußerlich 200, Tool intern **401** | Nein | Modell meldet „HTTP 401 Unauthorized", keine Beschreibung extrahierbar |
| 29.08.2026 | OpenRouter `web_fetch`, `engine: exa` | ImmoScout24 Exposé | äußerlich 200, Tool intern **fehlgeschlagen** | Nein | Kein Statuscode/Inhalt zurückgegeben, „fetch failed" |
| 29.08.2026 | OpenRouter `web_fetch`, `engine: parallel` | ImmoScout24 Exposé | äußerlich 200, Tool intern **fehlgeschlagen** | Nein | Kein Statuscode/Inhalt zurückgegeben, „fetch failed" |

**Ergebnis**: Kein einziger der vier getesteten Wege (roher `curl`, `web_fetch`/openrouter, `web_fetch`/exa, `web_fetch`/parallel) kommt an ImmoScout24 vorbei — deckt sich exakt mit dem bereits im Vorprojekt-Dokument notierten Stand. Damit greift laut der dort festgelegten Entscheidungsregel: **„nichts besteht → immobilienscout24.de fest auf das Einfügefeld (F-12) legen"**. Kleinanzeigen.de braucht dagegen überhaupt kein `web_fetch` — ein einfacher serverseitiger `httpx`-Request mit realistischem User-Agent reicht, spart die Fetch-Gebühr komplett und liefert `og:latitude`/`og:longitude` direkt ohne Geocoding-Schritt.

Der eigene Live-Test ist eine Einzelmessung an einem Tag (kein 24h-Wiederholungstest, wie im Vorprojekt-Dokument als Sorgfaltsmaßnahme vorgeschlagen) — für die endgültige Produktionsentscheidung sollte dieser Test laut dortiger Vorgabe noch einmal im Abstand von 24 Stunden wiederholt werden, da Bot-Blockaden sich ändern können.

## 8. Kosten pro Aufruf (eigene Live-Messwerte)

| Aufruf | Modell | Tool | Prompt-Tokens | Kosten |
|---|---|---|---|---|
| example.com Smoke-Test | gpt-4o-mini | web_fetch/openrouter | 410 | $0,0000867 |
| ImmoScout Exposé | gpt-4o-mini | web_fetch/openrouter | — | $0,000113 |
| ImmoScout Exposé | gpt-4o-mini | web_fetch/exa | — | $0,000128 |
| ImmoScout Exposé | gpt-4o-mini | web_fetch/parallel | — | $0,000198 |
| Haustyp ELK (json_schema) | gpt-4o-mini | web_fetch/openrouter | 10.713 | $0,0017558 |
| Haustyp ELK (json_schema) | gemini-2.5-flash-lite | web_fetch/openrouter (nicht aufgerufen) | 124 | $0,0000492 |
| Haustyp ELK (json_schema) | claude-haiku-4.5 | web_fetch/openrouter | 14.553 | $0,016958 |

**Beobachtung**: Bei realen, contentreichen Seiten (ELK-Herstellerseite) dominiert die Token-Menge der Seite die Kosten, nicht die Fetch-Gebühr selbst (die bei `engine: openrouter` ohnehin $0 ist). `claude-haiku-4.5` war beim identischen Task ca. 10× teurer als `gpt-4o-mini`, ohne ein besseres Schema-Ergebnis zu liefern — für dieses Extraktionsmuster ist `gpt-4o-mini` (oder ein vergleichbar günstiges Modell mit `structured_outputs`) die wirtschaftlichere Wahl, sofern die Zwei-Call-Lösung aus Abschnitt 5 verwendet wird.

## 9. Fehlercodes (aus OpenRouter-API-Referenz)

| Code | Bedeutung |
|---|---|
| 400 | Bad Request — ungültige/fehlende Parameter, CORS |
| 401 | Unauthorized — ungültige Credentials, abgelaufene OAuth-Session, deaktivierter/ungültiger API-Key |
| 402 | Payment Required — Guthaben des Keys/Accounts erschöpft |
| 403 | Forbidden — fehlende Berechtigung, Guardrail-Block oder Moderationsflag |
| 408 | Request Timeout |
| 429 | Too Many Requests — Rate Limit, mit `Retry-After`-Header |
| 502 | Bad Gateway — gewähltes Modell down oder ungültige Provider-Antwort |
| 503 | Service Unavailable — kein Provider erfüllt die Routing-Anforderungen |

Fehler tragen zusätzlich ein `error_type`-Feld für programmatische Auswertung; bei Streaming kommen Fehler als SSE-Event, da die HTTP-Header bereits gesendet sind. Für die Web-Fetch-/Web-Search-Tools gilt zusätzlich: Ein Fetch-Fehler (falsche Domain, 401/403 vom Zielserver, Timeout) erscheint **nicht** als HTTP-Fehlercode dieser Tabelle, sondern steckt im Tool-Ergebnis (`status: "failed"`) innerhalb einer ansonsten erfolgreichen 200er-Antwort — siehe Abschnitt 2 und die ImmoScout-Tests in Abschnitt 7.

## 10. Fallstricke — Zusammenfassung

1. **`response_format` + `tools` gemeinsam ist nicht verlässlich** (Abschnitt 5) — bei allen drei getesteten Modellen wurde das Schema ignoriert, sobald `web_fetch` im selben Call aktiv war. Zwei getrennte Calls verwenden.
2. **Fetch-Fehler sind kein HTTP-Fehler.** Der äußere Request bleibt 200; scheitern kann nur der interne Tool-Call. Prüflogik muss den Modelltext bzw. `server_tool_use_details` auswerten, nicht `response.status_code`.
3. **`web_fetch` liefert standardmäßig keine strukturierten Quell-Metadaten** (keine `annotations`/`url_citation` wie bei `web_search`) — wer `quelle_url` fürs Datenmodell braucht (wie im `Inserat`/`Haustyp`-Schema vorgesehen), muss das Modell explizit per Prompt/Schema dazu zwingen, die URL im Ergebnis zu wiederholen.
4. **Modellwahl beeinflusst, ob überhaupt gefetcht wird.** `gemini-2.5-flash-lite` hat den Tool-Call im Extraktions-Prompt schlicht verweigert („kann nicht garantieren, dass …") — für produktiven Einsatz vorher je Zielmodell mit einem echten Smoke-Test verifizieren, nicht nur anhand der `supported_parameters`-Liste.
5. **Web-Fetch- und Web-Search-Preise sind zwei getrennte Preistabellen** mit eigenen Engine-Kosten — in der Doku selbst schon leicht inkonsistent zwischen Versionen. Vor dem produktiven Kostenbudget lieber `usage.cost` aus echten Responses tracken als Dokupreise hart programmieren.
6. **ImmoScout24 blockiert auf WAF-Ebene (AWS WAF Challenge), nicht nur per User-Agent-Check** — das ist robuster als ein einfacher UA-Filter und wahrscheinlich auch von OpenRouters eigener Fetch-Infrastruktur (die vermutlich ähnliche IP-Ranges/kein Headless-Browser nutzt) nicht zu umgehen. Kein Aufwand in Workarounds stecken; F-12 (Einfügefeld) ist der stabile Weg für ImmoScout, wie im Vorprojekt-Dokument bereits festgelegt.
7. **`max_content_tokens` kürzt stillschweigend** — bei sehr langen Herstellerseiten (das ELK-Beispiel brauchte bereits 10.7k Prompt-Tokens bei `max_content_tokens: 8000`) ohne Fehlermeldung; bei Datenblatt-PDFs mit vielen Maßangaben ggf. höher setzen und die tatsächliche `usage.prompt_tokens` prüfen.

## 11. Verbrauchtes Budget dieses Tests

Live per `GET https://openrouter.ai/api/v1/key` verifiziert:

| Zeitpunkt | `usage` (verbraucht) | `limit_remaining` (übrig) |
|---|---|---|
| Vor dem ersten bezahlten Call | $0,000000 | $2,000000 |
| Nach allen 7 bezahlten Calls | **$0,0022812** | **$1,9977188** |

Insgesamt 7 bezahlte `chat/completions`-Aufrufe getätigt (Budget-Vorgabe: max. 8): 1× Smoke-Test `web_fetch`/example.com, 3× ImmoScout-Entscheidungsexperiment (Engines openrouter/exa/parallel), 3× Haustyp-Extraktion mit `json_schema` (gpt-4o-mini, gemini-2.5-flash-lite, claude-haiku-4.5). `GET /api/v1/key` und `GET /api/v1/models` wurden mehrfach kostenlos genutzt. **Verbraucht: $0,0023 von $2,00 (0,11 %). Übrig: $1,9977 (99,89 %).**
