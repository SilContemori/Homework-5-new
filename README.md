# Bozza ma bozza di Presentazione

clicca e vedi
[Apri bozza su Canva](https://www.canva.com/design/DAG4lonqIAI/Dm8cPcJ5jjjsiwdFBRj7WA/edit?utm_content=DAG4lonqIAI&utm_campaign=designshare&utm_medium=link2&utm_source=sharebutton)

# Informazioni utili
Virtual Environment for Python 3.X.X (almeno 3.11)
```
python3.X -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -V
pip -V
```

Prima di installare le librerie, attivare l'ambiente virtuale con:
`source .venv/bin/activate`

e poi eseguire:
`pip install -r requirements.txt`
Per disattivare l'ambiente virtuale:
`deactivate`

Per far funzionare il progetto, avviare il docker-compose:
`docker-compose up -d````

Per fermare il docker-compose:
`docker-compose stop`
`docker-compose rm`
o semplicemente:
`docker-compose down `


Per avviare il progetto, eseguire:
`python run.py`
o dal file run.py cliccare con il tasto destro e selezionare "Run 'run.py'"

L'interfaccia grafica sarà disponibile su `http://localhost:5000`

per avviare i task, vai su `http://localhost:5000/docs` 