
Die REST-API nutzen:

curl -X POST -H "Content-Type: application/json" -d @working-input.json http://localhost:5002/api/convert

POST http://localhost:5002/api/convert - JSON-Daten konvertieren
GET http://localhost:5002/api/schema - JSON-Schema abrufen
GET http://localhost:5002/api/example - Beispiel-JSON-Datei abrufen

## Command-Line Tools nutzen:
cd /Users/muratkahriman/Documents/Cloud/jconverter
source .venv/bin/activate
python3 ./scripts/parse-json-and-ixbrl.py working-input.json output.html