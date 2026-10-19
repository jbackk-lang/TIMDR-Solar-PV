# Portable Windows x64

Paczka zawiera kod Solar-PV, CPython 3.12.10 oraz zależności z `requirements-lock.txt`. Użytkownik rozpakowuje ZIP i uruchamia `START.bat`; nie wykonuje instalacji ani poleceń pip.

- `START.bat`: otwiera lokalny dashboard; ponowne uruchomienie wykorzystuje działającą instancję tej paczki.
- `STOP.bat`: kończy pracę wyłącznie tej instancji.
- `TESTY.bat`: uruchamia dołączone testy.
- `runtime/server.log`: dziennik uruchomienia.
- `BUILD-MANIFEST.json`: wersje bibliotek, wersja źródeł i skrót środowiska Python.

Zajęty port 5001 powoduje wybór wolnego portu. Kod aplikacji pozostaje w `app/`, bez historii Git, lokalnego środowiska deweloperskiego i danych użytkownika. Zawarte biblioteki zachowują pliki licencji i metadane dystrybucji. Paczka nie zmienia systemowego Pythona.

## Budowanie

Na Windows x64 z Pythonem 3.12 i pip:

```powershell
python portable/build_portable.py --output dist/TIMDR-Solar-PV-portable
```

Budowanie wymaga internetu do pobrania oficjalnego środowiska Python i bibliotek. Gotowa paczka działa offline dla lokalnego demo i analizy danych. Opcjonalnie `--runtime-zip` wskazuje wcześniej pobrany oficjalny ZIP, a `--site-packages` pozwala użyć zaufanego środowiska Windows CPython 3.12 x64 z wersjami zgodnymi z plikiem lock.

Po zbudowaniu uruchom testy i sprawdź start/stop z przeniesionego katalogu. Do ZIP-a nie dodawaj katalogu runtime z wynikami własnej pracy. Wydanie zawiera oddzielny plik SHA256SUMS do sprawdzenia integralności pobranego archiwum.
