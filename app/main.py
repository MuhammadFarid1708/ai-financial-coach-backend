import re
import uuid
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Depends, HTTPException, status, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

# Internal app architecture imports
from app.database import engine, Base, get_db
from app.models import User, FinancialProfile, AIInsight
from app.schemas import UserCreate, UserResponse, FinancialProfileCreate, FinancialProfileResponse
from app.ai_service import generate_financial_coaching_insight
from app.security import get_password_hash, verify_password, create_access_token

# ==============================================================================
# 1. INITIALIZE APP & MIDDLEWARE
# ==============================================================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# 2. DATABASE SCHEMAS & SYNCHRONIZATION 
# ==============================================================================
class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False) 
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

Base.metadata.create_all(bind=engine)

# ==============================================================================
# 3. PYDANTIC REQUEST BODIES
# ==============================================================================
class ChatRequest(BaseModel):
    prompt: str
    salary: float
    debt: float
    surplus: float
    session_id: Optional[str] = None

class ProfileSaveRequest(BaseModel):
    user_id: UUID
    username: str
    monthly_income: float
    monthly_expenses: float
    savings_goal: float
    risk_tolerance: str

class SessionCreateRequest(BaseModel):
    user_id: UUID
    title: str

class InsightSaveRequest(BaseModel):
    user_prompt: str
    session_id: str
    conversational_response: str
    chart_data: Optional[dict] = None

# ==============================================================================
# 4. API ROUTE ENDPOINTS
# ==============================================================================

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI Financial Coach API Gateway!"}


# --- AUTHENTICATION ---

@app.post("/auth/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="An account with this email already exists."
        )
    
    new_user = User(
        email=user.email, 
        username=user.username, 
        password=get_password_hash(user.password)
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/login")
def login(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == username).first()
    
    # Fix: Use your local verification helper to check the text against your hash
    if not user or not verify_password(password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    token_payload = {
        "sub": str(user.id), 
        "username": user.username or user.email.split('@')[0]
    }
    access_token = create_access_token(data=token_payload)
    
    return {
        "access_token": access_token, 
        "token_type": "bearer", 
        "user_id": str(user.id),
        "username": user.username
    }

# --- FINANCIAL PROFILES ---

@app.post("/api/save-profile")
def save_financial_profile(request: ProfileSaveRequest, db: Session = Depends(get_db)):
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == request.user_id).first()
    
    if profile:
        profile.monthly_income = request.monthly_income
        profile.monthly_expenses = request.monthly_expenses
        profile.savings_goal = request.savings_goal
        profile.risk_tolerance = request.risk_tolerance
    else:
        profile = FinancialProfile(
            user_id=request.user_id,
            monthly_income=request.monthly_income,
            monthly_expenses=request.monthly_expenses,
            savings_goal=request.savings_goal,
            risk_tolerance=request.risk_tolerance
        )
        db.add(profile)

    user_record = db.query(User).filter(User.id == request.user_id).first()
    if user_record:
        user_record.username = request.username

    db.commit()
    return {"status": "success", "message": "Financial metrics saved directly into PostgreSQL tables successfully!"}


@app.get("/profile/{user_id}", response_model=FinancialProfileResponse)
def get_profile(user_id: str, db: Session = Depends(get_db)):
    try:
        db_user_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format for user_id.")

    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == db_user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Financial profile not found.")
    return profile


@app.delete("/profile/{user_id}")
def delete_profile(user_id: str, db: Session = Depends(get_db)):
    try:
        db_user_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format for user_id.")

    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == db_user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Financial profile not found to delete.")
    db.delete(profile)
    db.commit()
    return {"message": "Financial profile successfully deleted."}


# --- CONVERSATIONAL ENGINE WITH FINANCIAL RELEVANCE GUARDRAILS ---

@app.post("/api/chat")
async def financial_chat(request: ChatRequest, db: Session = Depends(get_db)):
    prompt_text = request.prompt.lower()
    salary = request.salary
    unavoidable = request.debt  
    surplus = request.surplus

    target_amount = 0
    is_loan = "loan" in prompt_text or "emi" in prompt_text
    is_tax = any(word in prompt_text for word in ["tax", "evade", "legal", "deduction", "corporate", "save tax"])

    lakh_match = re.search(r'(\d+)\s*(l|lakh)', prompt_text)
    k_match = re.search(r'(\d+)\s*k', prompt_text)
    raw_match = re.search(r'(\d{4,8})', prompt_text)

    if lakh_match:
        target_amount = int(lakh_match.group(1)) * 100000
    elif k_match:
        target_amount = int(k_match.group(1)) * 1000
    elif raw_match:
        target_amount = int(raw_match.group(1))

    # Identify target asset name
    item = None
    finance_keywords = ["bike", "car", "house", "home", "flat", "phone", "laptop", "sofa", "innova", "invest", "save", "budget", "salary", "spend", "expense"]
    for word in finance_keywords:
        if word in prompt_text:
            if word in ["bike", "car", "house", "home", "flat", "phone", "laptop", "sofa", "innova"]:
                item = word
            break

    # ─── FIXED: FINANCE RELEVANCE GUARDRAIL CHECK ───
    timeline_modifiers = ["month", "mos", "mo", "year", "yrs", "yr", "from savings", "through savings", "use money", "what if", "what abt"]
    is_valid_followup = any(mod in prompt_text for mod in timeline_modifiers)
    
    # Verify if history exists to prevent false positives on fresh out-of-scope prompts
    has_session_history = False
    if request.session_id:
        try:
            session_uuid = uuid.UUID(request.session_id)
            history_check = db.query(AIInsight).filter(AIInsight.session_id == session_uuid).first()
            if history_check:
                has_session_history = True
        except Exception:
            pass

    if not is_tax and not is_loan and target_amount == 0 and item is None and not is_valid_followup:
        return {
            "strategy": "I can only assist with financial planning, budget strategies, tax optimization, and asset acquisition modeling. I can't reply to this prompt.",
            "chart_data": None
        }

    # ─── DEEP CONVERSATIONAL CONTEXT RECOVERY MATRIX ───
    if (target_amount == 0 or item is None) and request.session_id:
        try:
            session_uuid = uuid.UUID(request.session_id)
            past_insights = db.query(AIInsight).filter(AIInsight.session_id == session_uuid).order_by(AIInsight.id.desc()).limit(10).all()
            
            for insight in past_insights:
                if not insight.user_prompt:
                    continue
                past_prompt = insight.user_prompt.lower()
                
                if target_amount == 0:
                    p_lakh = re.search(r'(\d+)\s*(l|lakh)', past_prompt)
                    p_k = re.search(r'(\d+)\s*k', past_prompt)
                    p_raw = re.search(r'(\d{4,8})', past_prompt)
                    if p_lakh: target_amount = int(p_lakh.group(1)) * 100000
                    elif p_k: target_amount = int(p_k.group(1)) * 1000
                    elif p_raw: target_amount = int(p_raw.group(1))
                
                if item is None:
                    for word in ["bike", "car", "house", "home", "flat", "phone", "laptop", "sofa", "innova"]:
                        if word in past_prompt:
                            item = word
                            break
                            
                if target_amount > 0 and item is not None:
                    break
                    
        except Exception as memory_err:
            print(f"Deep context memory lookup failed: {memory_err}")

    # Safety boundary check if context tracing yields no variables on a generic empty session thread
    if target_amount == 0 and not is_tax and not is_loan:
        return {
            "strategy": "I can only assist with financial planning, budget strategies, tax optimization, and asset acquisition modeling. I can't reply to this prompt.",
            "chart_data": None
        }

    if not item:
        item = "asset"

    # ==========================================================================
    # BRANCH A: CORPORATE AND TAX SHIELD ENGINE
    # ==========================================================================
    if is_tax:
        gross_revenue = salary
        baseline_opex = unavoidable
        effective_tax_rate = 0.2517
        
        raw_taxable_ebit = max(0.0, gross_revenue - baseline_opex)
        unoptimized_tax_provision = round(raw_taxable_ebit * effective_tax_rate, 2)
        
        legal_tax_shield_deductions = round(raw_taxable_ebit * 0.45, 2)
        optimized_taxable_ebit = max(0.0, raw_taxable_ebit - legal_tax_shield_deductions)
        optimized_tax_provision = round(optimized_taxable_ebit * effective_tax_rate, 2)
        legal_tax_saved = round(unoptimized_tax_provision - optimized_tax_provision, 2)
        
        final_corporate_net_profit = round(gross_revenue - baseline_opex - legal_tax_shield_deductions - optimized_tax_provision, 2)

        status_message = (
            f"🏛️ CORPORATE TAX MITIGATION & ASSET SHIELD REPORT\n"
            f"--------------------------------------------------------\n"
            f"Analysis Type: Legal Tax Avoidance Framework | Gross Metrics Monitored: ₹{gross_revenue:,}\n\n"
            f"1. STRATEGIC REVENUE SHIELDING ANALYSIS (Section 37(1)):\n"
            f"• Baseline Unoptimized Tax Exposure: ₹{unoptimized_tax_provision:,}\n"
            f"• Optimized AI Tax Shield Provision: ₹{optimized_tax_provision:,}\n"
            f"• Total Capital Retained Legally: +₹{legal_tax_saved:,} / month\n"
            f"• Post-Tax Net Retained Profit Margin: ₹{final_corporate_net_profit:,}\n\n"
            f"2. COMPULSORY LEGAL IMPLEMENTATION VECTORS:\n"
            f"To legally lower your corporate tax liability without triggering an audit, your entity must maximize business expenditure structures before striking your net profit line:\n"
            f"• Operational Depreciation: Write off machinery, server infrastructure, and electronics under specialized higher block rates (up to 40% WDV).\n"
            f"• Salary & Perquisite Splitting: Route personal expenses (Vehicle Leases, Fuel Reimbursements, Living Utilities) as corporate perquisites to make them 100% tax-deductible to the company.\n"
            f"• Marketing & Research Inflows: Allocate up to ₹{legal_tax_shield_deductions:,} into direct revenue-generating operating channels like advertisement, domain acquisitions, or business consulting contracts.\n\n"
            f"3. FISCAL COMPLIANCE AND AUDIT SAFEGUARDS:\n"
            f"Ensure all shifted expenditures are supported by explicit invoices, commercial agreements, and corporate resolutions. Do not use cash for payments over ₹2,000 to remain fully compliant."
        )

        return {
            "strategy": status_message,
            "chart_data": {
                "labels": ["Targeted Savings", "Essential Needs", "Lifestyle Wants"],
                "values": [baseline_opex + legal_tax_shield_deductions, final_corporate_net_profit, optimized_tax_provision]
            }
        }

    # ==========================================================================
    # BRANCH B: AMORTIZED DEBT / LONG-TERM LOAN ENGINE
    # ==========================================================================
    elif is_loan and target_amount > 0:
        annual_rate = 0.085
        monthly_rate = annual_rate / 12
        tenure_months = 180
        
        emi_numerator = target_amount * monthly_rate * ((1 + monthly_rate) ** tenure_months)
        emi_denominator = ((1 + monthly_rate) ** tenure_months) - 1
        needed_per_month = round(emi_numerator / emi_denominator, 2)
        
        pay_from_savings = any(term in prompt_text for term in ["from savings", "through savings", "pay emi through my savings", "use money from saving"])

        if pay_from_savings:
            target_savings_pie = max(0.0, surplus - needed_per_month)
            essential_needs_pie = unavoidable + needed_per_month
            lifestyle_wants_pie = max(0.0, salary - surplus - unavoidable)
            
            status_message = (
                f"📊 DEBT LIABILITY ANALYSIS: HOUSING LOAN STRUCTURE (SAVINGS FUNDED)\n"
                f"--------------------------------------------------------\n"
                f"Asset Target: {item.upper()} | Loan Principal: ₹{target_amount:,} | Estimated Tenure: 15 Years (180 Mos)\n\n"
                f"1. MORTGAGE EMI DETAILED BREAKDOWN:\n"
                f"• Assumed Interest Rate: 8.5% per annum (Standard Indian Retail Base Rate)\n"
                f"• Calculated Monthly Mortgage EMI: ₹{needed_per_month:,} / month\n"
                f"• Total Debt-to-Income Impact: {round((needed_per_month / salary) * 100, 2)}% of total inflow\n\n"
                f"2. CAPITAL FEASIBILITY ADVICE (SAVINGS REALLOCATION):\n"
                f"The monthly mortgage EMI of ₹{needed_per_month:,} has been dynamically routed out of your core active investment target. Your lifestyle spending remains entirely unchanged.\n\n"
                f"3. WEALTH DISTRIBUTION IMPACT PATHWAY:\n"
                f"Your active monthly wealth building threshold compresses down from ₹{surplus:,} to ₹{target_savings_pie:,} to shield your wants budget."
            )
        else:
            target_savings_pie = surplus
            essential_needs_pie = unavoidable + needed_per_month
            lifestyle_wants_pie = max(0.0, salary - target_savings_pie - essential_needs_pie)
            available_cash_for_emi = salary - surplus - unavoidable
            
            if available_cash_for_emi >= needed_per_month:
                status_message = (
                    f"📊 DEBT LIABILITY ANALYSIS: HOUSING LOAN STRUCTURE\n"
                    f"--------------------------------------------------------\n"
                    f"Asset Target: {item.upper()} | Loan Principal: ₹{target_amount:,} | Estimated Tenure: 15 Years (180 Mos)\n\n"
                    f"1. MORTGAGE EMI DETAILED BREAKDOWN:\n"
                    f"• Calculated Monthly Mortgage EMI: ₹{needed_per_month:,} / month\n"
                    f"• Total Debt-to-Income Impact: {round((needed_per_month / salary) * 100, 2)}% of total inflow\n\n"
                    f"2. CAPITAL FEASIBILITY ADVICE:\n"
                    f"Your financial profile comfortably accommodates this long-term liability. Your baseline savings goal of ₹{surplus:,} remains entirely untouched.\n\n"
                    f"3. ASSET RISK IMPACT PATHWAY:\n"
                    f"Your fixed unavoidable overhead will shift from ₹{unavoidable:,} to ₹{unavoidable + needed_per_month:,} to reflect the recurring debt obligation."
                )
            else:
                status_message = (
                    f"🚨 DEBT LIABILITY ANALYSIS: LEVERAGE CAPACITY EXCEEDED\n"
                    f"--------------------------------------------------------\n"
                    f"Asset Target: {item.upper()} | Loan Principal: ₹{target_amount:,} | Estimated Tenure: 15 Years (180 Mos)\n\n"
                    f"Your core cash flow parameters cannot clear this loan amount safely without structural realignments."
                )
            
        return {
            "strategy": status_message,
            "chart_data": {
                "labels": ["Targeted Savings", "Essential Needs", "Lifestyle Wants"],
                "values": [target_savings_pie, essential_needs_pie, lifestyle_wants_pie]
            }
        }

    # ==========================================================================
    # BRANCH C: CASH SAVINGS ADVANCED INCREMENTAL ENGINE
    # ==========================================================================
    elif target_amount > 0:
        months = 1 
        
        month_match = re.search(r'(\d+)\s*(month|mos|mo)', prompt_text)
        year_match = re.search(r'(\d+)\s*(year|yrs|yr)', prompt_text)

        if month_match:
            months = int(month_match.group(1))
        elif year_match:
            months = int(year_match.group(1)) * 12

        if months <= 0:
            months = 1

        needed_per_month = round(target_amount / months, 2)
        
        target_savings_pie = needed_per_month
        essential_needs_pie = unavoidable
        lifestyle_wants_pie = max(0.0, salary - target_savings_pie - essential_needs_pie)

        if surplus >= needed_per_month:
            extra_savings_needed = 0.0
            retained_surplus_buffer = round(surplus - needed_per_month, 2)
            
            status_message = (
                f"📊 INCREMENTAL CAPITAL ALLOCATION ANALYSIS\n"
                f"--------------------------------------------------------\n"
                f"Asset Target: {item.upper()} | Capital Required: ₹{target_amount:,} | Horizon: {months} Months\n\n"
                f"1. QUANTITATIVE ACQUISITION METRICS:\n"
                f"• Target Monthly Savings Rate Required: ₹{needed_per_month:,} / month\n"
                f"• Existing Configured Savings Surplus: ₹{surplus:,} / month\n"
                f"• Additional Out-of-Pocket Savings Required: ₹{extra_savings_needed:,} / month\n\n"
                f"2. STRATEGIC REALIGNMENT REPORT:\n"
                f"You do NOT need to increase your savings rate or sacrifice any extra lifestyle variance. Your configured monthly savings goal of ₹{surplus:,} completely absorbs the required ₹{needed_per_month:,} capital rate.\n\n"
                f"3. RESIDUAL SURPLUS RUNWAY:\n"
                f"After prioritizing ₹{needed_per_month:,} exclusively toward your {item}, you retain a secondary wealth generation cushion of ₹{retained_surplus_buffer:,} / month within your active portfolio framework."
            )
        else:
            extra_savings_needed = round(needed_per_month - surplus, 2)
            
            status_message = (
                f"🚨 SHORTFALL MATRIX: DISCRETIONARY BUDGET COMPRESSION\n"
                f"--------------------------------------------------------\n"
                f"Asset Target: {item.upper()} | Capital Required: ₹{target_amount:,} | Horizon: {months} Months\n\n"
                f"1. TARGET DEFICIT BREAKDOWN:\n"
                f"• Target Monthly Savings Rate Required: ₹{needed_per_month:,} / month\n"
                f"• Existing Configured Savings Surplus: ₹{surplus:,} / month\n"
                f"• Net Incremental Savings Needed: +₹{extra_savings_needed:,} / month\n\n"
                f"2. COMPULSORY ALLOCATION ADJUSTMENT:\n"
                f"Your current savings baseline cannot clear this asset timeline. To hit your timeline target, you must manually save an additional ₹{extra_savings_needed:,} every single month by squeezing your Discretionary Lifestyle budget down to size."
            )

        return {
            "strategy": status_message,
            "chart_data": {
                "labels": ["Targeted Savings", "Essential Needs", "Lifestyle Wants"],
                "values": [target_savings_pie, essential_needs_pie, lifestyle_wants_pie]
            }
        }

    default_wants = max(0.0, salary - surplus - unavoidable)
    return {
        "strategy": "Tell me what corporate metrics, tax queries, or capital asset plans you want to review!",
        "chart_data": {
            "labels": ["Targeted Savings", "Essential Needs", "Lifestyle Wants"],
            "values": [surplus, unavoidable, default_wants]
        }
    }


@app.post("/profile/{user_id}/insights")
def create_ai_insight(user_id: str, request: InsightSaveRequest, db: Session = Depends(get_db)):
    try:
        db_user_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="The provided user_id is not a valid UUID format.")
    
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == db_user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Please create a financial profile for this user first.")
    
    try:
        active_session_id = uuid.UUID(request.session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="The provided session_id is not a valid UUID format.")
    
    try:
        new_insight = AIInsight(
            user_id=profile.user_id,
            session_id=active_session_id,
            user_prompt=request.user_prompt,
            conversational_response=request.conversational_response,
            chart_bool=True if request.chart_data else False,
            chart_data=request.chart_data
        )
        db.add(new_insight)
        db.commit()
    except Exception as db_err:
        print(f"Database sync failed: {db_err}")
        raise HTTPException(status_code=500, detail=f"Database log save failure: {str(db_err)}")
    
    return {"status": "Success", "message": "Full transaction details logged into ai_insights successfully."}


@app.get("/history/{user_id}/sessions")
def get_user_chat_sessions(user_id: str, db: Session = Depends(get_db)):
    try:
        db_user_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format for user_id.")

    history = db.query(AIInsight).filter(AIInsight.user_id == db_user_id).order_by(AIInsight.id.desc()).all()
    return [
        {
            "id": item.id,
            "session_id": item.session_id,
            "user_prompt": item.user_prompt,
            "conversational_response": item.conversational_response,
            "chart_bool": item.chart_bool,
            "chart_data": item.chart_data
        }
        for item in history
    ]


@app.get("/api/sessions/{user_id}")
def get_user_sessions(user_id: UUID, db: Session = Depends(get_db)):
    return db.query(ChatSession).filter(ChatSession.user_id == str(user_id)).order_by(ChatSession.created_at.desc()).all()


@app.post("/api/sessions")
def create_new_session(request: SessionCreateRequest, db: Session = Depends(get_db)):
    new_id = str(uuid.uuid4())
    new_session = ChatSession(id=new_id, user_id=str(request.user_id), title=request.title)
    db.add(new_session)
    db.commit()
    return {"status": "success", "session_id": new_id, "title": request.title}


@app.delete("/api/sessions/{session_id}")
def delete_chat_session(session_id: str, db: Session = Depends(get_db)):
    session_obj = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session_obj:
        db.delete(session_obj)
        
    try:
        session_uuid = uuid.UUID(session_id)
        db.query(AIInsight).filter(AIInsight.session_id == session_uuid).delete()
    except ValueError:
        pass
        
    db.commit()
    return {"status": "success", "message": "Strategy thread successfully dropped from PostgreSQL records."}