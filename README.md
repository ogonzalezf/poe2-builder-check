# POE 2 Builder Check

Ventanita flotante que puntúa de 1 a 10 los items de Path of Exile 2 según tu build.

## Uso

1. Instala [Python](https://www.python.org/) marcando "Add Python to PATH".
2. Pon el juego en modo ventana sin bordes.
3. Abre `Iniciar.bat`.
4. En el juego, pasa el cursor sobre un item y pulsa Ctrl+C.

La ventana se arrastra con el ratón y se cierra con clic derecho.

Modo prueba, sin ventana: `python poe2_checker.py item.txt`

## Cómo puntúa

Los pesos del build están en `pesos.json` y se releen en cada item:

- `stats`: cada stat tiene un `patron` (regex sobre el texto del item) o un valor `derivado` (`pdps`, `edps`, `res_total`), y un valor `bueno` a partir del cual cuenta al 100%.
- `grupos`: qué clases de item pertenecen a cada grupo y el `peso` de cada stat en él.
- `mods_para_10`: cuántos de los stats más importantes, en su valor bueno, hacen falta para un 10.
- `personaje`: nivel y atributos, para avisar de requisitos que no cumples.

El programa solo lee el portapapeles; no toca la memoria del juego. Por ahora reconoce el cliente en inglés.
