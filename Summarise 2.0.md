# 🧾 Specification: Zero-Input Expense Splitting System

---

## 🎯 System Goal

Automatically:
- Identify transaction participants
- Split the amount
- Create debts
- (Optionally) automatically settle them

**Without manual user input in 80–95% of cases**

---

## 🧩 Architecture (High Level)

### Components:

1. **Transaction Ingestor**
   - Sources:
     - Open Banking (PSD2 API)
     - Direct bank integrations
   - Data:
     - amount
     - merchant
     - timestamp
     - geolocation (if available)

---

2. **Context Engine (product core)** ⭐
Determines:
- who participated
- which group the transaction belongs to

---

3. **Split Engine**
- calculates shares
- applies rules

---

4. **Ledger**
- stores "who owes whom"

---

5. **Settlement Engine**
- automatic debt settlement

---

6. **User Interface**
- confirmations
- corrections

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
- geo_zones (optional)
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

### Context (generated)
- group_id
- participants
- confidence_score

---

### Split
- transaction_id
- shares (map user → amount)

---

## 🧠 Context Engine — Core Logic

### Input:
- transaction
- user history
- geolocation
- social graph

---

### Algorithm (Priority Order)

#### 1. Merchant → Group mapping
Examples:
- Uber → "trips"
- Lidl → "household"

---

#### 2. Geo clustering
If:
- multiple users nearby
→ consider them participants

---

#### 3. Temporal pattern
- Friday evening → friends
- Weekday morning → work

---

#### 4. Behavioral history
- recurring patterns

---

#### 5. Explicit overrides
- user corrections

---

### Output:
- participants = [A, B, C]
- group = "trip_spain"
- confidence = 0.87

## ⚙️ Split Engine

### Rule system (declarative)
```
IF merchant_category == "restaurant"
THEN split = equal

IF merchant == "rent"
THEN split = fixed_ratio

IF merchant_category == "groceries"
THEN split = ignore
```

---

### Edge cases:
- user exclusions
- custom weights
- rounding

---

## 🤖 Automation Logic

### Decision thresholds:
- confidence > 0.8 → auto apply
- 0.5–0.8 → passive confirmation
- < 0.5 → ask user

---

### Passive confirmation UX:
> "Split €42 between you and Anna — OK?"

No response → treated as confirmed

---

## 💸 Settlement Engine

### Options:

#### A. Manual (MVP)
- ledger only

---

#### B. Semi-auto
- push notification for payment

---

#### C. Full auto
- periodic netting
- automatic transfers

---

## 🔐 Privacy / Security

- PSD2 consent
- granular permissions
- local processing (where possible)
- explainability:
  - "Why did the system make this decision?"

---

## 📱 UX Requirements

Minimize user actions:
- no manual amount input
- no participant selection (ideally)

User actions limited to:
- confirmations
- corrections

---

## 🚀 MVP Scope

1. Bank connection
2. Manual groups
3. Auto-suggest split
4. One-tap confirm
5. Simple rules

---

## 🧠 Moat (Competitive Advantage)

- social graph
- behavioral data
- Context Engine accuracy

---

## ❗ Limitations

100% automation is possible only if:
- all participants are in the system
- transaction access available
- context available (geo / behavioral)

Otherwise:
→ realistic 80–90% automation

---

## 💡 Future Vision

Integration with offline stores:
- system knows:
  - who's at the register
  - who's in the group
  - what was purchased

→ potentially 100% automation

---
