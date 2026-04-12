# LedgerMind Benchmark Suite

Полный набор бенчмарков для сравнительного анализа производительности LedgerMind в различных режимах и на разных датасетах.

## 📊 Что тестируется

### Режимы (Modes)
| Режим | Описание | Когда использовать |
|-------|----------|-------------------|
| `full` | LedgerMind с векторным поиском + keyword + RRF ranking | Production, максимальное качество |
| `keyword` | Только SQLite FTS5 (без векторов) | Быстрый поиск, мобильные устройства |
| `baseline_sql` | Прямой SQLite FTS5 без LedgerMind фич | Базовая линия для сравнения |
| `baseline_flat` | Упрощённый LedgerMind без ConflictEngine | Тестирование overhead |

### Датасеты
| Датасет | Тип | Сложность | Размер |
|---------|-----|-----------|--------|
| `locomo` | Реальные диалоги | Средняя | 1000 записей |
| `longmemeval` | Сложные временные связи | Высокая | 1000 записей |
| `synthetic` | Синтетические данные | Низкая | Любой |

### Метрики
- **Latency**: p50, p95 (ms) для записи и поиска
- **Throughput**: ops/sec (операций в секунду)
- **Recall@5**: % правильных результатов в топ-5
- **MRR**: Mean Reciprocal Rank (средний обратный ранг)
- **Precision@5**: Точность в топ-5

## 🚀 Быстрый старт

### Запуск полного сравнительного бенчмарка
```bash
# Из корня проекта
.venv/bin/python benchmarks/run_all.py
```

Это запустит **все режимы** на **всех датасетах** и создаст сравнительный отчёт.

### Запуск отдельного бенчмарка

#### Latency & Scalability
```bash
# Полный режим на LoCoMo (быстрый тест: 1K, 5K)
.venv/bin/python benchmarks/latency_bench.py --mode full --dataset locomo --fast

# Keyword режим на LongMemEval (полный тест: 1K, 5K, 10K, 20K)
.venv/bin/python benchmarks/latency_bench.py --mode keyword --dataset longmemeval

# Baseline на синтетике
.venv/bin/python benchmarks/latency_bench.py --mode baseline_sql --dataset synthetic --fast
```

#### Retrieval Accuracy
```bash
# Full режим на LoCoMo
.venv/bin/python benchmarks/agentic_bench.py --mode full --dataset locomo --scale 1000

# Keyword на LongMemEval с JSON выводом
.venv/bin/python benchmarks/agentic_bench.py --mode keyword --dataset longmemeval --output-json
```

### Анализ результатов
```bash
# Сравнительный анализ всех результатов
.venv/bin/python benchmarks/compare_modes.py
```

## 📁 Структура результатов

После запуска в `benchmarks/results/` появятся:

```
benchmarks/results/
├── scalability_full_locomo_20260412_120000.csv      # Latency/throughput
├── scalability_keyword_locomo_20260412_120500.csv
├── scalability_baseline_sql_locomo_20260412_121000.csv
├── agentic_metrics_full_20260412_120000.json        # Accuracy (JSON)
├── agentic_metrics_keyword_20260412_120500.json
├── comparative_report_20260412_121500.md            # Сравнительный отчёт
├── latency_comparison_locomo.png                    # Графики
├── throughput_comparison_locomo.png
└── recall_comparison_locomo.png
```

## 📊 Пример результатов (LoCoMo dataset)

| Mode | Operation | Scale | p50 (ms) | p95 (ms) | Throughput | Recall@5 |
|------|-----------|-------|----------|----------|------------|----------|
| **full** | write | 1000 | ~280 | ~400 | ~3.5 | - |
| **full** | search | 1000 | ~180 | ~250 | ~0.5 | **~95%** |
| **keyword** | write | 1000 | ~220 | ~337 | ~4.2 | - |
| **keyword** | search | 1000 | ~161 | ~205 | ~0.42 | **90%** |
| **baseline_sql** | write | 1000 | ~50 | ~70 | ~15 | - |
| **baseline_sql** | search | 1000 | ~10 | ~15 | ~50 | **~70%** |

**Ключевые выводы:**
- ✅ Full режим даёт **+5% recall** vs keyword (95% vs 90%)
- ⚠️ Full режим имеет **+180% latency** vs baseline
- ✅ Keyword-only — хороший баланс скорости и качества

## 🔧 Параметры

### latency_bench.py
```
--mode       Режим: full, keyword, baseline_flat, baseline_sql (default: full)
--dataset    Датасет: synthetic, locomo, longmemeval (default: synthetic)
--fast       Быстрый тест (только 1K и 5K)
```

### agentic_bench.py
```
--mode         Режим: full, keyword, baseline_flat, baseline_sql (default: full)
--dataset      Датасет: synthetic, locomo, longmemeval (default: locomo)
--scale        Количество записей (default: 1000)
--output-json  Сохранить результаты в JSON
```

## 🎯 Когда запускать

| Сценарий | Что запускать | Частота |
|----------|--------------|---------|
| **Регрессионное тестирование** | `run_all.py --fast` | При каждом PR |
| **Полный бенчмарк** | `run_all.py` | Перед релизом |
| **Быстрая проверка** | `latency_bench.py --mode full --dataset locomo --fast` | При изменении core |
| **Анализ overhead** | `compare_modes.py` | После полного бенчмарка |

## 📈 Визуализация

`compare_modes.py` автоматически генерирует:
- **Latency Comparison** - grouped bar chart латентности по режимам
- **Throughput Comparison** - пропускная способность по режимам
- **Recall Comparison** - точность поиска по режимам
- **Comparative Report** - Markdown таблица с метаданными

## 🐛 Troubleshooting

### ModuleNotFoundError: No module named 'benchmarks'
Запускайте через `.venv/bin/python` или установите PYTHONPATH:
```bash
export PYTHONPATH="$PWD:$PWD/src"
python benchmarks/latency_bench.py
```

### Отсутствуют зависимости
```bash
.venv/bin/pip install numpy pandas matplotlib rich psutil
```

### Датасет не найден
Убедитесь, что файлы датасетов существуют:
```bash
git ls-files --others benchmarks/datasets/
# Должно показать:
# benchmarks/datasets/locomo/data.jsonl
# benchmarks/datasets/longmemeval/s_cleaned.json
```

## 📝 История изменений

### 2026-04-12 — Major Refactor
- ✅ Добавлена поддержка реальных датасетов (LoCoMo, LongMemEval)
- ✅ Сравнительный запуск всех режимов в `run_all.py`
- ✅ Новый скрипт анализа `compare_modes.py`
- ✅ JSON вывод для agentic бенчмарков
- ✅ Улучшенные графики сравнения в `utils.py`
- ✅ Автоматический overhead анализ
- ✅ Исправлены импорты для прямого запуска

### Ранее
- Синтетические данные только в `latency_bench.py`
- Только `keyword` режим в `run_all.py`
- Без сравнительных графиков
