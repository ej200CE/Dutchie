# 🧾 ТЗ: Система автоматического деления расходов (Zero-Input Expense Splitting)

---

## 🎯 Цель системы

Автоматически:
- определять участников платежа  
- делить сумму  
- создавать долги  
- (опционально) автоматически их закрывать  

**Без ручного ввода со стороны пользователя в 80–95% случаев**

---

## 🧩 Архитектура (высокий уровень)

### Компоненты:

1. **Transaction Ingestor**
   - Источники:
     - Open Banking (PSD2 API)
     - Прямые интеграции с банками
   - Данные:
     - сумма  
     - merchant  
     - время  
     - геолокация (если есть)

---

2. **Context Engine (ядро продукта)** ⭐  
Определяет:
- кто участвовал  
- к какой группе относится транзакция  

---

3. **Split Engine**
- рассчитывает доли  
- применяет правила  

---

4. **Ledger**
- хранит “кто кому должен”  

---

5. **Settlement Engine**
- авто-погашение долгов  

---

6. **User Interface**
- подтверждения  
- исправления  

---

## 📊 Data Model

### User
- id  
- bank_connections  
- social_graph  

---

### Group
- id  
- members  
- default_rules  
- geo_zones (опционально)  
- merchant_whitelist  

---

### Transaction
- id  
- amount  
- merchant  
- timestamp  
- location  
- payer  

---

### Context (генерируется)
- group_id  
- participants  
- confidence_score  

---

### Split
- transaction_id  
- shares (map user → amount)

---

## 🧠 Context Engine — ключевая логика

### Вход:
- транзакция  
- история пользователя  
- геолокация  
- социальный граф  

---

### Алгоритм (приоритеты)

#### 1. Merchant → Group mapping
Пример:
- Uber → “поездки”  
- Lidl → “дом”  

---

#### 2. Geo clustering
Если:
- несколько пользователей рядом  
→ считаем их участниками  

---

#### 3. Temporal pattern
- пятница вечер → друзья  
- утро будни → работа  

---

#### 4. Behavioral history
- повторяющиеся паттерны  

---

#### 5. Explicit overrides
- пользовательские корректировки  

---

### Выход:
# 🧾 ТЗ: Система автоматического деления расходов (Zero-Input Expense Splitting)

---

## 🎯 Цель системы

Автоматически:
- определять участников платежа  
- делить сумму  
- создавать долги  
- (опционально) автоматически их закрывать  

**Без ручного ввода со стороны пользователя в 80–95% случаев**

---

## 🧩 Архитектура (высокий уровень)

### Компоненты:

1. **Transaction Ingestor**
   - Источники:
     - Open Banking (PSD2 API)
     - Прямые интеграции с банками
   - Данные:
     - сумма  
     - merchant  
     - время  
     - геолокация (если есть)

---

2. **Context Engine (ядро продукта)** ⭐  
Определяет:
- кто участвовал  
- к какой группе относится транзакция  

---

3. **Split Engine**
- рассчитывает доли  
- применяет правила  

---

4. **Ledger**
- хранит “кто кому должен”  

---

5. **Settlement Engine**
- авто-погашение долгов  

---

6. **User Interface**
- подтверждения  
- исправления  

---

## 📊 Data Model

### User
- id  
- bank_connections  
- social_graph  

---

### Group
- id  
- members  
- default_rules  
- geo_zones (опционально)  
- merchant_whitelist  

---

### Transaction
- id  
- amount  
- merchant  
- timestamp  
- location  
- payer  

---

### Context (генерируется)
- group_id  
- participants  
- confidence_score  

---

### Split
- transaction_id  
- shares (map user → amount)

---

## 🧠 Context Engine — ключевая логика

### Вход:
- транзакция  
- история пользователя  
- геолокация  
- социальный граф  

---

### Алгоритм (приоритеты)

#### 1. Merchant → Group mapping
Пример:
- Uber → “поездки”  
- Lidl → “дом”  

---

#### 2. Geo clustering
Если:
- несколько пользователей рядом  
→ считаем их участниками  

---

#### 3. Temporal pattern
- пятница вечер → друзья  
- утро будни → работа  

---

#### 4. Behavioral history
- повторяющиеся паттерны  

---

#### 5. Explicit overrides
- пользовательские корректировки  

---

### Выход:
- participants = [A, B, C]
- group = "trip_spain"

## ⚙️ Split Engine

### Rule system (декларативный)
- confidence = 0.87
IF merchant_category == "restaurant"
THEN split = equal
IF merchant == "rent"
THEN split = fixed_ratio
IF merchant_category == "groceries"
THEN split = ignore

---

### Edge cases:
- исключения пользователей  
- кастомные веса  
- округление  

---

## 🤖 Automation Logic

### Decision thresholds:
- confidence > 0.8 → auto apply  
- 0.5–0.8 → passive confirmation  
- < 0.5 → запрос пользователю  

---

### Passive confirmation UX:
> “Разделили 42€ между вами и Анной — ок?”  

Если нет ответа → считается подтверждённым  

---

## 💸 Settlement Engine

### Варианты:

#### A. Manual (MVP)
- только ledger  

---

#### B. Semi-auto
- push на оплату  

---

#### C. Full auto
- периодический netting  
- автоматические переводы  

---

## 🔐 Privacy / Security

- PSD2 consent  
- granular permissions  
- локальная обработка (где возможно)  
- explainability:
  - “Почему система приняла это решение”  

---

## 📱 UX требования

Минимум действий:
- нет ручного ввода сумм  
- нет выбора участников (в идеале)  

Пользователь делает только:
- подтверждения  
- исправления  

---

## 🚀 MVP Scope

1. Подключение к банку  
2. Ручные группы  
3. Auto-suggest split  
4. One-tap confirm  
5. Простые правила  

---

## 🧠 Moat (конкурентное преимущество)

- social graph  
- поведенческие данные  
- accuracy Context Engine  

---

## ❗ Ограничения

100% автомат возможен только если:
- все участники в системе  
- есть доступ к транзакциям  
- доступен контекст (гео / поведение)  

Иначе:
→ реалистично 80–90% автоматизации  

---

## 💡 Расширение (Future Vision)

Интеграция с офлайн-магазинами:
- система знает:
  - кто у кассы  
  - кто в группе  
  - что куплено  

→ потенциально 100% автоматизация

---
