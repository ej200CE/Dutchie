# USE CASE: Automatic Trip Expense Splitting

---

## 1. Use Case Information

| Attribute | Value |
|-----------|-------|
| **Name** | Automatic Trip Expense Splitting |
| **Version** | 1.2 |
| **Status** | In Development |
| **Priority** | High |
| **Scope** | Mobile Application |

---

## 2. Description

The application **fully automatically** analyzes bank transactions and photos from trip participants WITHOUT any user interaction during the trip. The system identifies relevant expenses and distributes them fairly among participants.

### Key Paradigm: FULL AUTOMATION WITHOUT INTERACTION

**During the trip:**
- ✅ User should NOT choose, click, or comment on anything
- ✅ App works in the background, analyzing all expenses
- ✅ System automatically understands who participates in what expenses
- ❌ No pop-ups, requests, or confirmations

**After the trip (optional):**
- 🔧 User can make corrections if they want
- 🔧 But it's not required - baseline distribution is already fair
- 🔧 Corrections take 1-2 minutes for the entire trip

### Key Feature: Analysis of Receipt and Table Photos

The application uses computer vision to analyze receipt and table photos to determine:
- **What was ordered** - recognition of dishes and drinks in photos
- **Who ate what** - matching each person's photos with their plates/glasses
- **Accurate distribution** - instead of simple equal split, calculation based on actual consumption

This achieves fair expense distribution with acceptable accuracy (±5-15%), which is enough for friends. Over a longer trip, inaccuracies average out.

---

## 3. Actors

### Primary:
- **App User** - trip participant who grants access to their data

### Secondary:
- **Banking System** - source of transaction information
- **Device Gallery** - source of photos
- **Face Recognition AI/ML Engine** - identifies people count and identity
- **OCR (Optical Character Recognition) System** - recognizes text on receipts
- **Dish Analysis AI System** - recognizes dish and drink types in photos
- **Computer Vision System** - analyzes table composition and determines which dish belongs to which person

---

## 4. Preconditions

1. ✓ User has installed the app on their mobile device
2. ✓ User has an active bank account
3. ✓ User granted the app permission to access:
   - Photo gallery
   - Bank account
   - Device dates/times
4. ✓ Minimum 2 users participate in one trip

---

## 5. Main Flow

### Step 1: Trip Initialization (ONE TIME)
1. User opens the app
2. Selects "New Trip"
3. Specifies:
   - Trip name
   - Start date
   - End date
   - List of participants (or adds later)
4. **Clicks "Start" and forgets about the app during the trip**

### Step 2: BACKGROUND SYNCHRONIZATION (without user participation)

**DURING TRIP (automatically in background):**
1. App continuously connects to user's bank account
2. Automatically downloads all new transactions
3. Scans photo gallery for new photos
4. Analyzes found photos (receipts, tables, selfies)
5. **User sees nothing, confirms nothing, continues relaxing**

### Step 3: AUTOMATIC EXPENSE CATEGORIZATION (without requests)

**App self-determines expense type:**
1. **Filters transactions by trip dates**
2. **Identifies pre-trip payments** (hotel booking, car rental):
   - ✓ Payment date precedes trip start
   - ✓ Amount is significant → "Group expense for all"
3. **Identifies expenses during trip:**
   - Restaurants and food (bank: MCC codes 5812, 5814, 5411, etc.)
   - Services and tickets (ski lifts, museums, excursions)
   - Entertainment (parks, clubs, sports)
   - Personal purchases (pharmacy, clothing stores)
4. **Determines expense TYPE automatically - user does NOT choose**

### Step 4: Photo Analysis
1. App analyzes photos taken during trip days
2. Uses AI/ML to recognize:
   - Number of people in photos
   - Participant identities (if available)
   - Context (airport, restaurant, activity, etc.)
3. Creates "presence timeline" for each participant

### Step 4.1: Receipt Photo Analysis
1. App identifies receipt photos in gallery
2. Uses OCR to recognize text:
   - Restaurant/store name
   - Date and time
   - List of items and their costs
   - Total amount
3. Matches information with bank transaction
4. Creates detailed item registry for each payment

### Step 4.2: Table and Dish Photo Analysis
1. App identifies photos of table with food
2. Uses Computer Vision to recognize:
   - Number of dishes/plates/drinks
   - Type of each dish (pizza, pasta, soup, etc.)
   - Position of dishes relative to people in photo
3. Creates "table map" - which dish is in front of whom
4. Gets approximate cost of each dish from restaurant menu (if available)

### Step 4.3: Matching Dishes with Participants
1. App analyzes photos of each participant
2. Uses CV to determine:
   - Which dishes person holds or has in front of them
   - Which drinks they consumed
   - Approximate portion size (full, half, etc.)
3. Creates "consumption profile" for each participant
4. If person not on table photo, uses indirect data (time in restaurant, presence in other photos)

### Step 5: Smart Expense Distribution by Type (without requests)

**App SELF-determines how to distribute each expense:**

#### Rule 1: Housing/Transport Group Expenses
**Applies to:** Hotel booking, car rental, group tickets
- ✅ **Distributed equally among ALL participants** for full duration
- ℹ️ No user choice - app sees this is a group expense

#### Rule 2: Activities and Services (if one paid)
**Applies to:** Excursion, museum ticket, equipment rental
- ✅ If **whole group was in photos** → **distributed equally**
- ✅ If **someone wasn't there** → excluded from this expense
- ℹ️ System checks photos automatically, no asking

#### Rule 3: Restaurants with Photo Analysis (PRIORITY)
**Applies to:** Expenses with receipt + table photos uploaded
- 🍽️ If receipt photo AND table photo exist:
  - OCR recognizes all items
  - CV determines who ate what
  - **Each person pays for what they actually ate/drank**
  - Accuracy ±10-15% (good enough)
- 📸 No photos → proceeds to Rule 4

#### Rule 4: Restaurants without Photo Analysis
**Applies to:** Expenses WITHOUT receipt/table photos
- 👥 Checks photos of participants in restaurant
- ✅ Who was in photos → pays equally
- ❌ Who wasn't there → doesn't pay
- ℹ️ No interaction - app sees in photos

#### Rule 5: Premium Services (personal choice)
**Applies to:** Expensive wine, spa service, personal massage
- 👤 If photo shows ONLY ONE person involved → **only they pay**
- ℹ️ App automatically sees this from photos

#### Rule 6: Personal Purchases
**Applies to:** Pharmacy, clothing, gifts
- 👤 If MCC code indicates personal store AND person was alone → **only they pay**
- 🤝 If group was in store → distributed equally

**KEY:** All rules apply AUTOMATICALLY without any user choice

### Step 6: BACKGROUND CALCULATION (during trip)
1. **App continuously recalculates final payments:**
   - Analyzes new expenses as they appear
   - Applies automatic rules
   - Updates final calculation
2. **User SEES NOTHING AND CONFIRMS NOTHING**
   - System just works in background
   - No confirmation notifications

### Step 7: SHOW RESULTS (ONLY AFTER TRIP ENDS)
1. **Trip ended → user opens app**
2. **Sees final settlement:**
   - Detailed list of all expenses with categories
   - How each expense was distributed and why
   - Total payment amounts
3. **Can make corrections (optional):**
   - Edit expense categorization
   - Change who to include/exclude
   - Add comments
4. **Clicks "Complete" and done!**

---

## 6. Alternative Flows

**⚠️ IMPORTANT:** All these flows available ONLY AFTER trip ends! No corrections or choices during trip.

### 6.1 Manual Add Expense (POST-TRIP)
**Condition**: User wants to add expense not automatically detected

**Flow**:
1. User selects "Add Expense Manually"
2. Specifies amount, category, date
3. Selects participants included in expense
4. App adds expense to calculation

### 6.2 Correct Automatic Distribution (POST-TRIP)
**Condition**: App incorrectly determined expense participants

**Flow**:
1. User clicks on expense
2. Sees proposed distribution
3. Can edit participant list
4. Confirms changes

### 6.3 Exclude Expense (POST-TRIP)
**Condition**: Expense was automatically added but shouldn't be split

**Flow**:
1. User clicks expense in post-trip report
2. Selects "Exclude from shared expenses" or "Only for me"
3. App recalculates final payments

### 6.4 Add Participant Later (POST-TRIP)
**Condition**: Not all participants at trip start (setup error)

**Flow**:
1. User clicks "Add Participant" in post-trip report
2. Selects contact and specifies join date
3. App recalculates expenses, excluding those before join date

### 6.5 Correct Photo Analysis (POST-TRIP)
**Condition**: System incorrectly recognized dishes or distributed them

**Flow**:
1. User clicks on restaurant expense
2. Sees receipt photo and recognized items
3. Can manually edit dish-to-person assignments
4. App automatically recalculates fair distribution

### 6.6 Upload Photo Manually (POST-TRIP)
**Condition**: User wants to add expense info via photos

**Flow**:
1. User clicks expense
2. Selects "Upload Receipt" or "Upload Table Photo"
3. Takes/selects photo
4. App analyzes and auto-fills information
5. User confirms or edits results

---

## 7. Postconditions

### Upon Success:
1. ✓ All relevant expenses automatically identified
2. ✓ Each expense automatically distributed among participants by fair rules
3. ✓ User DID NOTHING during trip (full automation)
4. ✓ After trip, user sees:
   - How much each person spent
   - How much each person owes/is owed
   - Detailed explanation of each expense
5. ✓ Final payment table is fair (±5-15% accuracy)
6. ✓ User can make corrections if desired (optional)
7. ✓ Results can be shared among participants

---

## 8. Extensions

### 8.1 Payment System Integration
- Automatic payment execution between participants
- Payment status tracking

### 8.2 Group Chat
- Discuss expenses directly in app
- Vote on disputed expenses

### 8.3 History and Statistics
- Track all trips
- Analyze expenses per person
- Predictions based on previous trips

### 8.4 Export and Reports
- Export to PDF, Excel
- Print receipts

---

## 9. Functional Requirements

| # | Requirement | Description |
|---|-------------|-------------|
| FR1 | Bank Connection | Secure connection to bank account via OAuth |
| FR2 | Photo Access | Analyze device photo gallery |
| FR3 | AI Analysis | Determine number of people in photos |
| FR4 | Expense Filtering | Automatically identify relevant transactions |
| FR5 | Time Binding | Match transaction times with photos |
| FR6 | Calculations | Mathematically correct expense distribution |
| FR7 | Editing | Manual correction capability |
| FR8 | Reports | Generate detailed reports |
| FR9 | OCR Recognition | Extract information from receipts (items, prices) |
| FR10 | Dish Recognition | Identify dish and drink types in photos |
| FR11 | Table Analysis | Determine which dish is in front of which person |
| FR12 | Intelligent Distribution | Calculate fair distribution based on actual consumption |
| FR13 | Restaurant Menu Support | Integrate with menus to get dish prices |
| FR14 | ZERO interaction during trip | User should NOT choose/confirm/click anything during trip |
| FR15 | Automatic Rules | 6 built-in rules for automatic expense categorization |
| FR16 | Background Processing | Continuous background analysis of new transactions and photos |
| FR17 | Post-Trip Corrections | Corrections available only after trip ends (optional) |

---

## 10. Non-Functional Requirements

| # | Requirement | Description |
|---|-------------|-------------|
| NFR1 | Security | Encrypt bank and photo data |
| NFR2 | Performance | Trip analysis < 30 seconds, OCR < 5 secs per photo |
| NFR3 | Scalability | Support up to 20 participants per group |
| NFR4 | Reliability | Data sync with cloud |
| NFR5 | User Interface | Intuitive design for mobile devices |
| NFR6 | AI/ML Accuracy | OCR accuracy > 95%, dish recognition > 85%, face recognition > 90% |
| NFR7 | User Acceptability | Final distribution error ±5-15% from ideal (acceptable for friends) |
| NFR8 | Offline Capability | Local cache OCR results for offline operation |
| NFR9 | ZERO interaction | Zero user requests, zero confirmation notifications during trip |
| NFR10 | Minimal Corrections | Average correction time after trip < 2 minutes (optional) |

---

## 11. Usage Examples

### Scenario 1: Barcelona Trip

**Participants**: Anna, Bob, Karl, Diana (4 people)
**Date**: June 1-7

**Expenses**:
1. **May 31** - Apartment booking: €600 (Anna) → €150 each
2. **June 1** - Car rental: €400 (Bob) → €100 each
3. **June 2** - Restaurant: €120 (Karl) → €40 each (Anna, Diana, Karl present)
4. **June 3** - Ski lift: €80 (Anna) → €40 each (Anna, Bob present)
5. **June 3** - Water in store: €5 (Diana) → Diana only

**Final Result**:
- Karl → Anna: €271.75
- Diana → Anna: €115
- Diana → Bob: €326.25

---

### Scenario 2: Restaurant Dinner with Photo Analysis

**Participants**: Vladimir, Inna, Tanya (3 people)
**Situation**: One paid €87, but different dishes and drinks

**Receipt Analysis**:
- Carbonara Pasta (€18) → Inna
- Bolognese Pasta (€16) → Vladimir  
- Primavera Pasta (€14) → Tanya
- Caesar Salad (€12) → €4 each
- Water (€4) → €1.33 each
- Bread (€3) → €1 each
- Premium Wine (€8) → Inna only

**Final Distribution**:
- Inna → Vladimir: €31
- Tanya → Vladimir: €21.67

---

## 12. Acceptance Criteria

- [ ] App correctly syncs bank data in background
- [ ] User sees NO requests/notifications during trip
- [ ] AI correctly identifies people in photos (accuracy > 90%)
- [ ] OCR correctly recognizes receipt text (accuracy > 95%)
- [ ] Expenses correctly distributed by automatic rules
- [ ] Final calculation has ±5-15% error (acceptable for friends)
- [ ] Post-trip user sees detailed report
- [ ] User can make corrections if desired (< 2 minutes)
- [ ] All data securely stored and protected
- [ ] App performs fast (trip analysis < 30 secs)
- [ ] Results logical and understandable to users

---

## 13. Risks

| Risk | Probability | Impact | Solution |
|-----|-----------|--------|----------|
| Incorrect people recognition | High | High | Use advanced AI, provide correction option |
| Incorrect dish recognition | Medium | Medium | Provide manual correction, use trained ML |
| OCR errors on receipts | Low | Medium | Use high-accuracy OCR, manual verification |
| Incorrect item-to-person matching | Medium | High | Use timestamps, ML for matching |
| Poor photo quality | High | Medium | Show user tips, require retake |
| Bank data security breach | Low | Critical | Use OAuth, encryption, security audits |
| Data sync delays | Medium | Medium | Caching, API optimization |
| User complexity | Medium | Medium | Intuitive UI, tutorials, automation |
| Photo privacy | Medium | High | Local processing, minimal storage, encryption |
| Different cuisines/cultures | Medium | Medium | Train on diverse data, continuous improvement |

---

## 14. Core Philosophy

### Principle: FULL AUTOMATION WITHOUT INTERACTION

**App should work as if it didn't exist during the trip.**

**What user should NOT do during trip:**
- ❌ Answer "who was that?"
- ❌ Answer "is this group expense?"
- ❌ Confirm expenses
- ❌ Choose expense categories
- ❌ Select participants
- ❌ Fill any dialogs

**Why This Matters:**
- Users want to relax, not fill forms
- Less interaction → higher usage
- ±5-15% accuracy automatically > 0% if user forgets
- Friends accept small inaccuracies if overall fair

---

## 15. Fair vs Perfect Distribution

**Key Insight**: System must be maximally fair WITHOUT user participation.

**Target: 85-90% fairness, not 100%**
- ±5-15% error is acceptable for friends
- Over long trip, inaccuracies average out
- ✅ "Approximately fair" automatically
- ❌ "Perfectly fair" manually (nobody will do it)

**Example**:
- €250 per person ± €25 = everyone happy ✅
- €250 per person ± €0 but 5 hours work = nobody does it ❌

---

## 16. Distribution Algorithm

```
FOR EACH EXPENSE:
  IF receipt photo AND table photo:
    1) OCR: recognize all items
    2) CV: recognize who in photos
    3) CV: determine who ate what
    4) Distribute items by consumption
    5) Share common items equally
    
  ELSE IF bank transaction AND presence photos:
    1) Determine who was present
    2) Distribute equally
    
  ELSE:
    Request manual input or photo upload

OUTPUT: Fair distribution with minimal info
```

---

## 17. Distribution Rules (Automatic)

1. **Group Housing/Transport** → Equal split for all
2. **Activities** → Split among those who participated
3. **Restaurants (with photos)** → Split by actual consumption
4. **Restaurants (no photos)** → Equal split among present
5. **Premium Services** → Only consumer pays
6. **Personal Purchases** → Only purchaser pays

---

## 18. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-18 | Initial use case with bank data and face recognition |
| 1.1 | 2026-04-18 | Added OCR, dish recognition, intelligent distribution |
| 1.2 | 2026-04-18 | Full automation paradigm, 6 auto rules, zero requests during trip |
| TBD | TBD | Planned expansions |

---
