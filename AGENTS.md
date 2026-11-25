# Instrucciones para agentes

## Git: sin commit ni push automáticos

- **No hagas `git commit` ni `git push` por tu cuenta.** Solo se hacen cuando el usuario lo pide de forma explícita en ese momento.
- Esto **prevalece sobre el skill `ub-mode`**, cuyas secciones "Commit and Push" ("commit often", "push to the main line at the end") no se aplican aquí.
- Al terminar un trabajo, deja los cambios sin confirmar, resume qué cambió y pregunta si se hace el commit. Si el usuario lo aprueba, propón commits pequeños y ordenados, y no hagas push hasta que lo pida.
- Tampoco crees ramas, hagas `rebase`, `reset` ni `amend` sin petición explícita.

## Herramientas de calidad (ub-mode)

Instaladas en `~/.local/share/ub-tools/` (`crapper`, `dryer`, `mutator`, clonadas juntas porque `mutator` busca `../crapper`). Los envoltorios están en `~/.local/bin/`. No uses enlaces simbólicos; cada envoltorio llama al intérprete del entorno virtual de su herramienta y fija `PYTHONUTF8=1` (en Windows evita errores de codificación).

```bash
crapper --no-coverage <ruta>   # complejidad; sin --no-coverage usa la cobertura
dryer <ruta>                   # duplicación
mutator <ruta>                 # mutation testing (necesita crapper)
```

Escriben sus resultados en `.metrics/`.
