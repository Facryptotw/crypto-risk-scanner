"""
加密貨幣風險分析工具 - Flask 後端（改進版：智能識別流動性池）
支援多鏈代幣的風險評估，自動排除LP池計算真實集中度
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import asyncio
import httpx
from datetime import datetime, timezone
import os

app = Flask(__name__)
CORS(app)

# 速率限制 - 大幅提高但仍有保護
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["2000 per day", "300 per hour"],
    storage_uri="memory://"
)

# ====== API KEYS ======
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "271ceeebc0a94dd9acfd11270f7984ca")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6ImUyYzA4Y2NiLTYwMjYtNGYyMy05NjAxLWE1YmZkZjY3NTc5ZiIsIm9yZ0lkIjoiNDc5NzU1IiwidXNlcklkIjoiNDkzNTY2IiwidHlwZUlkIjoiMGFjOWRiMGItNzliYi00Y2JjLTkyMGYtMzg2N2E1ODhhOWU0IiwidHlwZSI6IlBST0pFQ1QiLCJpYXQiOjE3NjIzODk1NTMsImV4cCI6NDkxODE0OTU1M30.J0rM0hxabvWMoaeQCncbOe_0j5cL4cqzilnImf_VZLc")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "aa75a2a5-8c15-4ec9-a257-bc15176b7ff8")

CHAIN_MAP = {
    "ethereum": {"ds": "ethereum", "be": "ethereum", "mo": "eth"},
    "bsc":      {"ds": "bsc",      "be": "bsc",      "mo": "bsc"},
    "base":     {"ds": "base",     "be": "base",     "mo": "base"},
    "polygon":  {"ds": "polygon",  "be": "polygon",  "mo": "polygon"},
    "arbitrum": {"ds": "arbitrum", "be": "arbitrum", "mo": "arbitrum"},
    "optimism": {"ds": "optimism", "be": "optimism", "mo": "optimism"},
    "avalanche":{"ds": "avalanche","be": "avalanche","mo": "avalanche"},
    "solana":   {"ds": "solana",   "be": "solana",   "mo": None},
}

# Solana 已知 DEX 程序 ID
KNOWN_DEX_PROGRAMS = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "Dooar9JkhdZ7J3LHN3A7YCuoGRUggXhQaG4kijfLGU2j": "Raydium CPMM",
}

# 已知鎖倉/質押程序
KNOWN_LOCK_PROGRAMS = {
    "CChTq6PthWU82YZkbveA3WDf7s97BWhBK4Vx9bmsT743": "Team Finance Lock",
}

def risk_judgement(daily_trading_value_change: float,
                   daily_price_change: float,
                   liquidity: float,
                   marketcap: float,
                   top10_pct: float | None):
    """風險判定核心邏輯"""
    threshold = marketcap * 0.05
    wash = (daily_trading_value_change >= 500) and (daily_price_change <= 5)
    lpi  = (liquidity <= threshold)

    if top10_pct is None or top10_pct < 0:
        conc_tier = "invalid"
        conc_text = "無數據"
    elif top10_pct <= 25:
        conc_tier = "low"
        conc_text = "持有度中下"
    elif top10_pct <= 35:
        conc_tier = "elevated"
        conc_text = "持有度集中(高風險!)"
    elif top10_pct <= 50:
        conc_tier = "high"
        conc_text = "持有度過於集中(危險!)"
    elif top10_pct <= 100:
        conc_tier = "severe"
        conc_text = "持有度超級集中(很危險!)"
    else:
        conc_tier = "severe"
        conc_text = "持有度超級集中(很危險!)"

    if wash and lpi and conc_tier in ("high", "severe"):
        combo = "洗量 + LPI + 高度集中 → 極高風險｜高機率 P&D / Rug"
    elif wash and lpi:
        combo = "洗量 + LPI → 極高風險｜假需求疑慮強"
    elif wash and conc_tier in ("high", "severe"):
        combo = "洗量 + 集中度高 → 高風險｜量能可被少數地址對敲"
    elif lpi and conc_tier in ("high", "severe"):
        combo = "LPI + 集中度高 → 高風險｜小資金可抬價且易收割"
    elif wash:
        combo = "僅洗量 → 中高風險｜量價背離"
    elif lpi:
        combo = "僅 LPI → 中高風險｜流動性不匹配"
    elif conc_tier in ("high", "severe"):
        combo = "僅集中度過高 → 中風險｜籌碼結構脆弱"
    else:
        combo = "三項未觸發 → 低風險（仍需檢查合約/團隊）"

    score = 0
    if wash: score += 2
    if lpi:  score += 2
    score += {"low":0, "elevated":1, "high":2, "severe":3}.get(conc_tier, 0)

    if score == 0: level = "低風險"
    elif score <= 2: level = "中風險"
    elif score <= 4: level = "中高風險"
    elif score <= 6: level = "高風險"
    else: level = "極高風險"

    return {
        "wash": wash, 
        "lpi": lpi, 
        "conc_tier": conc_tier, 
        "conc_text": conc_text,
        "threshold": threshold, 
        "combo": combo, 
        "score": score, 
        "level": level
    }

async def fetch_token_primary_pair(chain_ds: str | None, address: str):
    """獲取代幣的主要交易對"""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    pairs = data.get("pairs") or []
    if not pairs:
        return None
    if chain_ds:
        cand = [p for p in pairs if p.get("chainId") == chain_ds]
        if cand: pairs = cand
    best = max(pairs, key=lambda p: (p.get("liquidity", {}).get("usd") or 0))
    return best

def _vol(c: dict) -> float:
    return float(c.get("quoteVolume") or c.get("volume") or c.get("v") or 0.0)

async def fetch_volume_change_pct(chain_ds: str, pair_address: str) -> float | None:
    """計算交易量變化百分比"""
    async with httpx.AsyncClient(timeout=25) as client:
        to_ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        from_ts = to_ts - 48 * 3600 * 1000
        url = f"https://api.dexscreener.com/chart/dex/candles/{chain_ds}/{pair_address}"
        r = await client.get(url, params={"from": from_ts, "to": to_ts, "resolution": "1h"})
        candles = []
        if r.status_code == 200:
            js = r.json()
            candles = (js.get("data") or {}).get("candles") or []

        def compute_change(n):
            last_n = candles[-n:]
            prev_n = candles[-2*n:-n]
            if not last_n or not prev_n: return None
            v1 = sum(_vol(c) for c in last_n)
            v0 = sum(_vol(c) for c in prev_n)
            if v0 <= 0: return None
            return (v1 - v0) / v0 * 100.0

        if len(candles) >= 48:
            ch = compute_change(24)
            if ch is not None: return ch
        if len(candles) >= 24:
            ch = compute_change(12)
            if ch is not None: return ch

        latest = await client.get(f"https://api.dexscreener.com/latest/dex/pairs/{chain_ds}/{pair_address}")
        if latest.status_code == 200:
            ljs = latest.json()
            pair = (ljs.get("pairs") or [None])[0] or {}
            vol_h24 = ((pair.get("volume") or {}).get("h24")) or 0.0
            vol_h6  = ((pair.get("volume") or {}).get("h6")) or None
            if vol_h24 and vol_h6:
                est_prev24 = float(vol_h6) * 4.0
                if est_prev24 > 0:
                    return (float(vol_h24) - est_prev24) / est_prev24 * 100.0
    return None

async def classify_solana_holder(account_address: str, client: httpx.AsyncClient):
    """
    識別 Solana 賬戶類型
    返回: {"type": "liquidity_pool" | "lock_contract" | "wallet" | "unknown", ...}
    """
    url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    
    account_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [
            account_address,
            {"encoding": "jsonParsed"}
        ]
    }
    
    try:
        r = await client.post(url, json=account_request)
        if r.status_code != 200:
            return {"type": "unknown", "address": account_address}
        
        data = r.json()
        account_info = data.get("result", {}).get("value")
        
        if not account_info:
            return {"type": "unknown", "address": account_address}
        
        owner = account_info.get("owner")
        
        # 檢查是否為 DEX 流動性池
        if owner in KNOWN_DEX_PROGRAMS:
            return {
                "type": "liquidity_pool",
                "address": account_address,
                "dex": KNOWN_DEX_PROGRAMS[owner],
                "owner": owner
            }
        
        # 檢查是否為鎖倉合約
        if owner in KNOWN_LOCK_PROGRAMS:
            return {
                "type": "lock_contract",
                "address": account_address,
                "program": KNOWN_LOCK_PROGRAMS[owner],
                "owner": owner
            }
        
        # Token Program 擁有 = 普通錢包或 CEX
        if owner == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA":
            return {
                "type": "wallet",
                "address": account_address,
                "owner": owner
            }
        
        # 其他情況標記為 unknown
        return {
            "type": "unknown",
            "address": account_address,
            "owner": owner
        }
        
    except Exception as e:
        print(f"分類賬戶時出錯 {account_address}: {e}")
        return {"type": "unknown", "address": account_address}

async def fetch_top10_from_helius(token_address: str):
    """
    改進版：使用 Helius API 獲取 Solana 持幣數據
    自動識別並排除流動性池，計算真實集中度
    """
    if not HELIUS_API_KEY:
        return None
    
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
            
            # 1. 獲取總供應量
            supply_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenSupply",
                "params": [token_address]
            }
            
            r1 = await client.post(url, json=supply_request)
            if r1.status_code != 200:
                return None
            
            supply_data = r1.json()
            if "result" not in supply_data:
                return None
            
            supply_info = supply_data["result"]["value"]
            total_supply = int(supply_info["amount"])
            decimals = int(supply_info["decimals"])
            
            # 2. 獲取最大持幣賬戶
            holders_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "getTokenLargestAccounts",
                "params": [token_address]
            }
            
            r2 = await client.post(url, json=holders_request)
            if r2.status_code != 200:
                return None
            
            holders_data = r2.json()
            if "result" not in holders_data:
                return None
            
            accounts = holders_data["result"]["value"]
            
            # 3. 分類每個賬戶（取前 20 名進行分析）
            classified_holders = []
            for acc in accounts[:20]:
                address = acc.get("address")
                amount = int(acc.get("amount", 0))
                
                if not address or amount == 0:
                    continue
                
                # 識別賬戶類型
                classification = await classify_solana_holder(address, client)
                classified_holders.append({
                    "address": address,
                    "amount": amount,
                    "type": classification["type"],
                    "info": classification
                })
            
            if not classified_holders:
                return None
            
            # 4. 按類型分組
            lp_pools = [h for h in classified_holders if h["type"] == "liquidity_pool"]
            lock_contracts = [h for h in classified_holders if h["type"] == "lock_contract"]
            wallets = [h for h in classified_holders if h["type"] in ["wallet", "unknown"]]
            
            # 5. 計算各種指標
            
            # 全部前 10 名的集中度（包含 LP）
            all_top10 = classified_holders[:10]
            all_top10_sum = sum(h["amount"] for h in all_top10)
            all_top10_pct = (all_top10_sum / total_supply) * 100.0
            
            # 排除 LP 池後的前 10 名（這是主要指標）
            non_lp_holders = [h for h in classified_holders if h["type"] != "liquidity_pool"]
            non_lp_top10 = non_lp_holders[:10]
            non_lp_top10_sum = sum(h["amount"] for h in non_lp_top10)
            non_lp_top10_pct = (non_lp_top10_sum / total_supply) * 100.0 if non_lp_top10 else 0.0
            
            # LP 池總量
            lp_total = sum(h["amount"] for h in lp_pools)
            lp_pct = (lp_total / total_supply) * 100.0
            
            # 6. 構建詳細的持幣者分解
            breakdown_all = []
            for i, h in enumerate(all_top10):
                holder_pct = (h["amount"] / total_supply) * 100.0
                entry = {
                    "rank": i + 1,
                    "address": h["address"][:8] + "..." + h["address"][-6:],
                    "amount_pct": round(holder_pct, 2),
                    "type": h["type"]
                }
                
                # 如果是 LP 池，加上 DEX 名稱
                if h["type"] == "liquidity_pool":
                    entry["dex"] = h["info"].get("dex", "Unknown DEX")
                
                breakdown_all.append(entry)
            
            breakdown_non_lp = []
            for i, h in enumerate(non_lp_top10):
                holder_pct = (h["amount"] / total_supply) * 100.0
                breakdown_non_lp.append({
                    "rank": i + 1,
                    "address": h["address"][:8] + "..." + h["address"][-6:],
                    "amount_pct": round(holder_pct, 2),
                    "type": h["type"]
                })
            
            return {
                "pct": non_lp_top10_pct,  # 主要指標：排除 LP 的集中度
                "pct_with_lp": all_top10_pct,  # 參考：包含 LP 的集中度
                "lp_pct": lp_pct,  # LP 池總佔比
                "lp_count": len(lp_pools),  # LP 池數量
                "raw_sum": non_lp_top10_sum,
                "supply": total_supply,
                "source": "helius_enhanced",
                "breakdown": {
                    "top10_all": breakdown_all,  # 所有前 10 名（含 LP）
                    "top10_non_lp": breakdown_non_lp,  # 排除 LP 的前 10 名
                    "lp_pools": [
                        {
                            "address": h["address"][:8] + "..." + h["address"][-6:],
                            "amount_pct": round((h["amount"] / total_supply) * 100.0, 2),
                            "dex": h["info"].get("dex", "Unknown")
                        }
                        for h in lp_pools
                    ]
                }
            }
            
    except Exception as e:
        print(f"Helius 增強版錯誤: {e}")
        return None

async def moralis_get(path: str, params: dict):
    """Moralis API 請求"""
    if not MORALIS_API_KEY: 
        return None
    headers = {"X-API-Key": MORALIS_API_KEY, "accept": "application/json"}
    url = f"https://deep-index.moralis.io/api/v2.2{path}"
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        try:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            return None

async def fetch_top10_from_moralis(chain_key: str, token_address: str):
    """使用 Moralis API 獲取 EVM 鏈持幣數據"""
    mo = CHAIN_MAP.get(chain_key, {}).get("mo")
    if not mo: 
        return None
    
    meta_list = await moralis_get("/erc20/metadata", {"chain": mo, "addresses[]": token_address})
    if not meta_list or not isinstance(meta_list, list) or len(meta_list) == 0:
        return None
    
    token_meta = meta_list[0]
    decimals = token_meta.get("decimals")
    total_supply = token_meta.get("total_supply")
    
    if not decimals or not total_supply:
        return None
    
    try:
        decimals = int(decimals)
        total_supply = int(total_supply)
    except Exception:
        return None
    
    if total_supply <= 0:
        return None
    
    holders_response = await moralis_get(f"/erc20/{token_address}/owners", {"chain": mo, "limit": 100, "order": "DESC"})
    if not holders_response:
        return None
    
    holders = holders_response.get("result") or []
    if not holders:
        return None
    
    balances = []
    for holder in holders:
        balance_raw = holder.get("balance") or holder.get("balance_formatted")
        if balance_raw is None:
            continue
        
        try:
            balance_int = int(balance_raw)
            balances.append(balance_int)
        except ValueError:
            try:
                balance_float = float(balance_raw)
                balance_int = int(balance_float * (10 ** decimals))
                balances.append(balance_int)
            except Exception:
                pass
    
    if not balances:
        return None
    
    top10_balances = sorted(balances, reverse=True)[:10]
    top10_sum = sum(top10_balances)
    pct = (top10_sum / total_supply) * 100.0
    
    return {"pct": pct, "raw_sum": top10_sum, "supply": total_supply, "source": "moralis"}

async def fetch_top10_concentration(chain_key: str, token_address: str):
    """統一的持幣集中度獲取接口"""
    chain_key = chain_key.lower()
    
    if chain_key == "solana":
        he = await fetch_top10_from_helius(token_address)
        if he:
            return he
        return None
    
    mo = await fetch_top10_from_moralis(chain_key, token_address)
    return mo

async def analyze_token(address: str, chain: str = "auto"):
    """完整的代幣分析流程"""
    try:
        if chain != "auto":
            chain = chain.lower()
            if chain not in CHAIN_MAP:
                return {"error": f"不支援的鏈: {chain}"}
            ds_chain = CHAIN_MAP[chain]["ds"]
        else:
            auto_pair = await fetch_token_primary_pair(None, address)
            if not auto_pair:
                return {"error": "找不到交易對"}
            ds_chain = auto_pair.get("chainId")
            chain = next((k for k, v in CHAIN_MAP.items() if v["ds"] == ds_chain), ds_chain)

        pair = await fetch_token_primary_pair(ds_chain, address)
        if not pair:
            return {"error": "查無交易對"}

        pair_addr = pair.get("pairAddress")
        liq_usd = float((pair.get("liquidity") or {}).get("usd") or 0.0)
        price_chg_24h = float((pair.get("priceChange") or {}).get("h24") or 0.0)
        marketcap = float(pair.get("marketCap") or pair.get("fdv") or 0.0)

        vol_chg_pct = await fetch_volume_change_pct(ds_chain, pair_addr)
        if vol_chg_pct is None:
            vol_chg_pct = 0.0

        top10_info = await fetch_top10_concentration(chain, address)
        if top10_info:
            # 使用排除 LP 的集中度作為主要指標
            top10_pct = float(top10_info.get("pct", 0.0))
            top_src = top10_info.get("source")
        else:
            top10_pct = None
            top_src = "N/A"

        tj = risk_judgement(
            daily_trading_value_change=float(vol_chg_pct),
            daily_price_change=float(price_chg_24h),
            liquidity=float(liq_usd),
            marketcap=float(marketcap),
            top10_pct=top10_pct,
        )

        # 構建返回結果
        result = {
            "success": True,
            "chain": chain.upper(),
            "address": address,
            "data": {
                "liquidity": liq_usd,
                "marketcap": marketcap,
                "price_change_24h": price_chg_24h,
                "volume_change": vol_chg_pct,
                "top10_pct": top10_pct,
                "top10_source": top_src
            },
            "analysis": tj
        }

        # 如果有詳細的持幣者分解數據，加入結果
        if top10_info and "breakdown" in top10_info:
            result["holder_details"] = {
                "concentration_with_lp": top10_info.get("pct_with_lp"),
                "concentration_without_lp": top10_info.get("pct"),
                "lp_percentage": top10_info.get("lp_pct"),
                "lp_count": top10_info.get("lp_count"),
                "breakdown": top10_info["breakdown"]
            }

        return result
        
    except Exception as e:
        return {"error": str(e)}

@app.route('/')
def index():
    """首頁"""
    return render_template('index.html')

@app.route('/api/analyze', methods=['POST'])
@limiter.limit("50 per minute")
def analyze():
    """分析 API 端點"""
    data = request.json
    address = data.get('address', '').strip()
    chain = data.get('chain', 'auto').strip()
    
    if not address:
        return jsonify({"error": "請輸入合約地址"}), 400
    
    # 在新的事件循環中運行異步函數
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(analyze_token(address, chain))
    loop.close()
    
    return jsonify(result)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') != 'production'
    
    print("🚀 啟動加密貨幣風險分析工具（智能版）...")
    print(f"📊 運行在端口: {port}")
    print(f"🌍 模式: {'開發' if debug else '生產'}")
    print("✅ API Keys 已配置 (Moralis + Helius)")
    print("🔍 新功能: 智能識別流動性池，計算真實集中度")
    print("⚠️  速率限制: 每分鐘 50 次，每小時 300 次，每天 2000 次")
    print("")
    
    app.run(debug=debug, host='0.0.0.0', port=port)
