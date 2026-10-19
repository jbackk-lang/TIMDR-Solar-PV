# Sprawdzenie wydania portable — 2026-10-19

- Windows x64, dołączony CPython 3.12.10, bez korzystania z systemowych ścieżek Python.
- **17 testów projektu przeszło** w dołączonym środowisku (178,92 s).
- **8 kontroli paczki przeszło**: wybór wolnego portu, dashboard po przeniesieniu, lokalne zasoby wykresów, analiza demo, ponowny start tej samej instancji, kontrola tożsamości przy zatrzymaniu, zatrzymanie własnego serwera i zachowanie innego serwera.
- Sprawdzono kopię paczki w katalogu ze spacjami i polskimi znakami w nazwie.
- Demo `normal_operation`: 730 próbek, odpowiedź analizy poprawna, health score 1,0.
- Testy projektu obejmują również pozostałe scenariusze syntetyczne i sprzężenie PV–bateria. To nie jest nowa walidacja na pomiarach rzeczywistej instalacji PVDAQ.

Pierwsze przygotowanie długiego scenariusza demo może potrwać dłużej: projekt oblicza fizyczne warunki nasłonecznienia dla kolejnych dni. Sprawdzenie paczki nie zmienia algorytmów analizy ani progów modelu.

Aktualizacja 2026.10.19.1: zielony przycisk „Uruchom analizę”, biały tekst, kontrast 5,02:1, osobny stan po najechaniu oraz obramowanie fokusu klawiatury. Identyfikator przycisku i obsługa kliknięcia zostały zachowane; algorytmy obliczeń bez zmian.
