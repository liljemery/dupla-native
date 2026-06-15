# Plantilla Informe Coordinacion Tecnica

## Objetivo

Esta plantilla sirve para presentar resultados de coordinacion 2.5D a revisores reales sin mezclar:

- hallazgos defendibles
- ruido tecnico
- lectura ejecutiva
- detalle de soporte

## Estructura recomendada

### 1. Resumen ejecutivo

- alcance de la corrida
- cantidad de pares programados
- cantidad de hallazgos defendibles
- nivel de confianza dominante
- mensaje corto para reunion

### 2. Logica del reporte

- que se considera `primary`
- que se considera `debug`
- que entra como `hallazgo defendible`
- que queda como `validacion manual`

### 3. Criterio de lectura

#### Severidad

- `critical`: conflicto grande o repetido, con alta urgencia
- `high`: conflicto fuerte para la siguiente reunion
- `medium`: hallazgo usable, pero con validacion acotada
- `low`: señal debil, no vender como cierre final

#### Prioridad

- `P1`: revisar de inmediato
- `P2`: revisar en el ciclo actual
- `P3`: seguimiento o validacion manual

#### Confianza

- `high`: geometria y nivel trazables
- `medium`: util para coordinacion, pero no cierre final
- `low`: señal fragil, dejar fuera del resumen ejecutivo

### 4. Hallazgos defendibles

Tabla sugerida:

| ID | Prioridad | Severidad | Confianza | Nivel | Disciplinas | Ubicacion | Accion recomendada |
| --- | --- | --- | --- | --- | --- | --- | --- |

### 5. Hallazgos con validacion manual

Tabla sugerida:

| ID | Motivo | Nivel | Capas / fuentes | Manejo sugerido |
| --- | --- | --- | --- | --- |

### 6. Secciones por perfil

#### Arquitectura

- que debe revisar
- que se puede decidir en esta ronda
- que depende de otra disciplina

#### Electrico

- rutas o reservas a validar
- choques con estructura o arquitectura
- decisiones pendientes

#### Sanitario

- pasos, mangas, shafts o pendientes a validar
- choques con estructura o arquitectura
- decisiones pendientes

### 7. Ruido tecnico y soporte

- debug conflicts
- elementos suprimidos
- blockers del coordinate audit
- blockers del pair schedule
- hotspots como zonas de concentracion, no como veredicto

### 8. Archivos de apoyo

- `technical_coordination_report.md`
- `primary_incidents.md`
- `coordinate_audit.md`
- `hotspot_incidents.md`
- `debug_candidates.json`
