# Manual Test APS Viewer Calibration

## Checklist

1. Abrir viewer normal:

```text
http://localhost:8000/api/projects/{project_id}/viewer?coordinate_space=world
```

2. Confirmar que Autodesk Viewer carga el DWG traducido por APS.

3. Confirmar que los boxes aparecen usando bbox.

4. Abrir modo calibración:

```text
http://localhost:8000/api/projects/{project_id}/viewer?coordinate_space=world&calibrate=true
```

5. Alternar `world` / `model` desde el panel.

6. Cambiar `offset_x` y presionar “Aplicar”.

7. Confirmar visualmente que los boxes se mueven sin guardar.

8. Presionar “Guardar configuración”.

9. Refrescar navegador.

10. Confirmar que los boxes mantienen la nueva posición.

11. Activar “Mostrar centroides”.

12. Activar “Mostrar labels”.

13. Seleccionar un clash en el sidebar.

14. Confirmar que el panel muestra bbox raw y `viewer_bbox` transformado.

15. Presionar “Reset”.

16. Refrescar.

17. Confirmar que los boxes vuelven a coordenadas sin calibración custom.

## Demo sin APS

```text
http://localhost:8000/api/projects/demo/viewer?calibrate=true
```

El demo permite validar UI, sidebar, labels, centroides y transformación temporal sin depender de un derivative APS real.
