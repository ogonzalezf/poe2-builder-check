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

Los pesos están en `pesos.json` y se releen en cada item. Ahora mismo corresponden al build
"Huntress Spirit Walker Mono End Game" de Nicro4Fun.

- `stats`: cada stat tiene un `patron` (regex sobre el texto del item) o un valor `derivado` (`pdps`, `edps`, `res_total`), y un valor `bueno` por defecto.
- `grupos`: un grupo por slot. Se elige por `clases` (clase del item) o por `nombres` (un único concreto).
  - `pesos`: por stat, `peso`, `[peso, bueno]` o `[peso, bueno, minimo]`. `bueno` es el valor que pide la guía para ese slot.
  - `mods_para_10`: cuántos de los stats más importantes, en su valor bueno, hacen falta para un 10.
  - `obligatorios`: stats sin los cuales la nota no pasa de 4.
  - `consejo`: lo que pide la guía para ese slot; se muestra bajo la nota.
- `personaje`: nivel y atributos, para avisar de requisitos que no cumples.

El programa solo lee el portapapeles; no toca la memoria del juego. Por ahora reconoce el cliente en inglés.
