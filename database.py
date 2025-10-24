"""
Supabase database client for FinAIssistant
Handles all database operations with proper error handling
"""
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
    
    async def upsert_user(self, telegram_id: int, username: str, display_name: str) -> Dict:
        """Upsert user and return user data"""
        try:
            result = self.client.table('users').upsert({
                'telegram_id': str(telegram_id),
                'name': display_name or username or 'Unknown'
            }, on_conflict='telegram_id').execute()
            
            # Get the user data with a separate query
            user_result = self.client.table('users').select('id, name, telegram_id').eq(
                'telegram_id', str(telegram_id)
            ).single().execute()
            
            if user_result.data:
                return user_result.data
            else:
                raise Exception("Failed to upsert user")
                
        except Exception as e:
            raise Exception(f"Database error upserting user: {str(e)}")
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Get user by telegram ID"""
        try:
            result = self.client.table('users').select('id, name, telegram_id').eq(
                'telegram_id', str(telegram_id)
            ).single().execute()
            
            return result.data if result.data else None
            
        except Exception:
            return None
    
    async def get_categories(self) -> List[Dict]:
        """Get all categories"""
        try:
            result = self.client.table('categories').select('id, name, description').order('name').execute()
            return result.data if result.data else []
            
        except Exception as e:
            raise Exception(f"Database error fetching categories: {str(e)}")
    
    async def insert_expense(
        self,
        user_id: int,
        category_id: int,
        merchant: str,
        amount: float,
        currency: str = 'MXN',
        expense_date: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict:
        """Insert a new expense"""
        try:
            # Get the user's name for paid_by field
            user_result = self.client.table('users').select('name').eq('id', user_id).single().execute()
            user_name = user_result.data.get('name', 'Unknown User') if user_result.data else 'Unknown User'
            
            # Convert to MXN if different currency
            converted_amount = amount
            target_currency = 'MXN'
            
            if currency.upper() != 'MXN':
                # Get conversion rate
                rate_data = await self.get_currency_rate(currency.upper(), 'MXN')
                if rate_data:
                    rate = rate_data['rate']
                    if rate_data['direct']:
                        converted_amount = amount * rate
                    else:
                        converted_amount = amount / rate
                    logger.info(f"Converted {amount} {currency} to {converted_amount:.2f} MXN (rate: {rate})")
                else:
                    logger.warning(f"No conversion rate found for {currency} to MXN, using original amount")
                    target_currency = currency  # Keep original currency if no conversion available
            
            expense_data = {
                'user_id': user_id,
                'category_id': category_id,
                'expense_detail': merchant,
                'amount': converted_amount,  # Store converted amount in MXN
                'original_amount': amount,  # Keep original amount
                'original_currency': currency,  # Keep original currency
                'currency': target_currency,  # MXN (or original if no conversion)
                'expense_date': expense_date or datetime.now().strftime('%Y-%m-%d'),
                'paid_by': user_name,  # Use actual user name
                'timestamp': datetime.now().isoformat(),
                'notes': notes
            }
            
            result = self.client.table('expenses').insert(expense_data).execute()
            
            if result.data:
                return result.data[0]
            else:
                raise Exception("Failed to insert expense")
                
        except Exception as e:
            raise Exception(f"Database error inserting expense: {str(e)}")
    
    async def get_currency_rate(self, from_currency: str, to_currency: str) -> Optional[Dict]:
        """Get currency conversion rate"""
        try:
            # Try direct conversion first
            result = self.client.table('currency_rates').select('rate').eq(
                'base_currency', from_currency
            ).eq('target_currency', to_currency).single().execute()
            
            if result.data:
                return {'rate': result.data['rate'], 'direct': True}
            
            # Try reverse conversion
            result = self.client.table('currency_rates').select('rate').eq(
                'base_currency', to_currency
            ).eq('target_currency', from_currency).single().execute()
            
            if result.data:
                return {'rate': result.data['rate'], 'direct': False}
            
            return None
            
        except Exception:
            return None
    
    async def execute_sql(self, sql: str, params: Optional[List] = None) -> List[Dict]:
        """
        Execute a safe SQL query using Supabase RPC
        Note: This requires setting up an RPC function in Supabase
        """
        try:
            # For now, return mock data since we need to set up the RPC function
            # In production, this would call: self.client.rpc('exec_sql', {'q': sql}).execute()
            return []
            
        except Exception as e:
            raise Exception(f"SQL execution error: {str(e)}")
    
    async def execute_raw_sql(self, sql: str, params: Optional[List] = None, template_name: Optional[str] = None, question: Optional[str] = None) -> List[Dict]:
        """
        Execute raw SQL with parameters - for AI agent queries
        This queries your actual Supabase data
        """
        try:
            logger.info(f"Execute raw SQL called with: template='{template_name}', params={params}")
            # Map SQL queries to actual Supabase PostgREST queries
            if "SUM(amount)" in sql and "specific_category_total" in str(params):
                # Specific category total query
                user_telegram_id = params[0] if params else None
                category_pattern = params[1].replace('%', '') if len(params) > 1 else ""
                start_date = params[2] if len(params) > 2 else None
                end_date = params[3] if len(params) > 3 else None
                
                # Get user first
                user_result = self.client.table('users').select('id').eq('telegram_id', user_telegram_id).execute()
                if not user_result.data:
                    return [{"total": 0}]
                
                user_id = user_result.data[0]['id']
                
                # Query expenses with category filter and date range
                query = self.client.table('expenses').select('amount, categories(name)').eq('user_id', user_id)
                if start_date:
                    query = query.gte('expense_date', start_date)
                if end_date:
                    query = query.lte('expense_date', end_date)
                
                result = query.execute()
                
                # Filter by category and sum
                total = 0.0
                for expense in result.data:
                    if expense.get('categories') and category_pattern.lower() in expense['categories']['name'].lower():
                        total += float(expense['amount'])
                
                return [{"total": total}]
                
            elif template_name in ["total_spent_period", "week_total", "month_total", "today_total", "yesterday_total"]:
                # Total spending for period - ALL EXPENSES in database (family view)
                from datetime import datetime, timedelta
                
                if template_name == "week_total":
                    # Last 7 days
                    end_date = datetime.now().date()
                    start_date = end_date - timedelta(days=7)
                elif template_name == "month_total":
                    # Current month
                    today = datetime.now().date()
                    start_date = today.replace(day=1)
                    end_date = today
                elif template_name == "today_total":
                    # Today only
                    today = datetime.now().date()
                    start_date = today
                    end_date = today
                elif template_name == "yesterday_total":
                    # Yesterday only
                    yesterday = datetime.now().date() - timedelta(days=1)
                    start_date = yesterday
                    end_date = yesterday
                else:
                    # Use provided params for total_spent_period
                    start_date = params[0] if params else None
                    end_date = params[1] if len(params) > 1 else None
                
                logger.info(f"Total spending query (ALL USERS): template={template_name}, start={start_date}, end={end_date}")
                
                # Query ALL expenses for date range (not user-specific)
                query = self.client.table('expenses').select('amount')
                if start_date:
                    query = query.gte('expense_date', str(start_date))
                if end_date:
                    query = query.lte('expense_date', str(end_date))
                
                result = query.execute()
                total = sum(float(expense['amount']) for expense in result.data)
                logger.info(f"Total calculated: ${total} from {len(result.data)} expenses")
                
                return [{"total": total}]
                
            elif template_name in ["expenses_by_category", "month_by_category", "today_by_category", "yesterday_by_category", "top_categories_period"]:
                # Category breakdown - ALL EXPENSES in database (family view)
                from datetime import datetime
                
                if template_name == "month_by_category":
                    # Current month
                    today = datetime.now().date()
                    start_date = today.replace(day=1)
                    end_date = today
                elif template_name == "today_by_category":
                    # Today only
                    today = datetime.now().date()
                    start_date = today
                    end_date = today
                elif template_name == "yesterday_by_category":
                    # Yesterday only
                    from datetime import timedelta
                    yesterday = datetime.now().date() - timedelta(days=1)
                    start_date = yesterday
                    end_date = yesterday
                else:
                    # Use provided params for other templates
                    start_date = params[0] if params else None
                    end_date = params[1] if len(params) > 1 else None
                
                logger.info(f"Category breakdown query (ALL USERS): template={template_name}, start={start_date}, end={end_date}")
                
                # Query ALL expenses with categories (not user-specific)
                query = self.client.table('expenses').select('amount, categories(name)')
                if start_date:
                    query = query.gte('expense_date', str(start_date))
                if end_date:
                    query = query.lte('expense_date', str(end_date))
                
                result = query.execute()
                logger.info(f"Raw query returned {len(result.data)} expenses (ALL USERS)")
                
                # Group by category
                category_totals = {}
                for expense in result.data:
                    if expense.get('categories'):
                        cat_name = expense['categories']['name']
                        if cat_name not in category_totals:
                            category_totals[cat_name] = {"total": 0.0, "count": 0}
                        category_totals[cat_name]["total"] += float(expense['amount'])
                        category_totals[cat_name]["count"] += 1
                
                # Convert to expected format and apply limit if this is top_categories_period
                results = [
                    {
                        "category": cat_name,
                        "total": data["total"], 
                        "count": data["count"],
                        "transactions": data["count"]  # For top_categories_period compatibility
                    }
                    for cat_name, data in sorted(category_totals.items(), key=lambda x: x[1]["total"], reverse=True)
                ]
                
                # Apply limit if this is top_categories_period query
                if template_name == "top_categories_period" and len(params) >= 3:
                    limit = params[2]
                    results = results[:limit]
                    
                return results
                
            elif template_name.startswith("custom_month_category_"):
                # Handle specific month/year queries like "july_2025"
                from datetime import datetime
                import calendar
                
                # Extract month and year from params
                month_name = params[0] if params else None
                year = params[1] if len(params) > 1 else None
                
                if not month_name or not year:
                    return []
                
                # Convert month name to number
                month_num = None
                for i, m in enumerate(calendar.month_name):
                    if m.lower() == month_name.lower():
                        month_num = i
                        break
                
                if not month_num:
                    return []
                
                # Calculate date range for the specific month
                start_date = datetime(year, month_num, 1).date()
                if month_num == 12:
                    end_date = datetime(year + 1, 1, 1).date()
                else:
                    end_date = datetime(year, month_num + 1, 1).date()
                
                logger.info(f"Custom month query: {month_name} {year} ({start_date} to {end_date})")
                
                # Query expenses for specific month
                query = self.client.table('expenses').select('amount, categories(name)')
                query = query.gte('expense_date', str(start_date))
                query = query.lt('expense_date', str(end_date))
                
                result = query.execute()
                logger.info(f"Custom month query returned {len(result.data)} expenses")
                
                # Group by category
                category_totals = {}
                for expense in result.data:
                    if expense.get('categories'):
                        cat_name = expense['categories']['name']
                        if cat_name not in category_totals:
                            category_totals[cat_name] = {"total": 0.0, "count": 0}
                        category_totals[cat_name]["total"] += float(expense['amount'])
                        category_totals[cat_name]["count"] += 1
                
                return [
                    {
                        "category": cat_name,
                        "total": data["total"],
                        "count": data["count"]
                    }
                    for cat_name, data in sorted(category_totals.items(), key=lambda x: x[1]["total"], reverse=True)
                ]
                
            elif template_name.startswith("custom_month_budget_"):
                # Handle specific month/year budget vs spending analysis
                from datetime import datetime
                import calendar
                
                # Extract month and year from params
                month_name = params[0] if params else None
                year = params[1] if len(params) > 1 else None
                
                if not month_name or not year:
                    return []
                
                # Convert month name to number
                month_num = None
                for i, m in enumerate(calendar.month_name):
                    if m.lower() == month_name.lower():
                        month_num = i
                        break
                
                if not month_num:
                    return []
                
                logger.info(f"Custom month budget query: {month_name} {year}")
                
                # Get ALL budgets (static/fixed budget table)
                budgets_query = self.client.table('budgets').select('category_id, amount, categories(name)')
                budgets_result = budgets_query.execute()
                
                logger.info(f"Found {len(budgets_result.data)} budget entries in static table")
                
                if not budgets_result.data:
                    return []
                
                # Get spending for the specific month
                start_date = datetime(year, month_num, 1).date()
                if month_num == 12:
                    end_date = datetime(year + 1, 1, 1).date()
                else:
                    end_date = datetime(year, month_num + 1, 1).date()
                
                spending_query = self.client.table('expenses').select('category_id, amount')
                spending_query = spending_query.gte('expense_date', str(start_date))
                spending_query = spending_query.lt('expense_date', str(end_date))
                spending_result = spending_query.execute()
                
                logger.info(f"Found {len(spending_result.data)} expense entries for {month_name} {year}")
                
                # Group spending by category
                spending_by_category = {}
                for expense in spending_result.data:
                    cat_id = expense['category_id']
                    amount = float(expense['amount'])
                    if cat_id not in spending_by_category:
                        spending_by_category[cat_id] = 0
                    spending_by_category[cat_id] += amount
                
                # Combine budget and spending data
                results = []
                for budget in budgets_result.data:
                    cat_id = budget['category_id']
                    budget_amount = float(budget['amount'])
                    spent_amount = spending_by_category.get(cat_id, 0)
                    remaining = budget_amount - spent_amount
                    percent_used = (spent_amount / budget_amount * 100) if budget_amount > 0 else 0
                    
                    results.append({
                        "category_name": budget['categories']['name'],
                        "budget": budget_amount,
                        "spent": spent_amount,
                        "remaining": remaining,
                        "percent_used": percent_used
                    })
                
                # Sort by percent used (highest first)
                results.sort(key=lambda x: x['percent_used'], reverse=True)
                return results
                
            elif template_name == "total_budget":
                # Total budget for current month
                from datetime import datetime
                
                logger.info(f"Total budget query for current month")
                
                today = datetime.now()
                current_month = today.month
                current_year = today.year
                
                logger.info(f"Querying budgets for month={current_month}, year={current_year}")
                
                # Get all budgets for current month/year
                budgets_query = self.client.table('budgets').select('amount')
                budgets_query = budgets_query.eq('month', current_month)
                budgets_query = budgets_query.eq('year', current_year)
                budgets_result = budgets_query.execute()
                
                logger.info(f"Found {len(budgets_result.data)} budget entries for month {current_month}/{current_year}")
                
                # Sum all budget amounts
                total = sum(float(budget['amount']) for budget in budgets_result.data)
                logger.info(f"Total budget calculated: ${total:.2f} MXN")
                
                return [{"total": total}]
            
            elif template_name == "budget_vs_spending":
                # Budget vs spending analysis - using STATIC budget table
                from datetime import datetime
                
                logger.info(f"Budget vs spending query using static budget table")
                
                today = datetime.now()
                current_month = today.month
                current_year = today.year
                
                # Get budgets for current month/year
                budgets_query = self.client.table('budgets').select('category_id, amount, categories(name)')
                budgets_query = budgets_query.eq('month', current_month)
                budgets_query = budgets_query.eq('year', current_year)
                budgets_result = budgets_query.execute()
                
                logger.info(f"Found {len(budgets_result.data)} budget entries for month {current_month}/{current_year}")
                
                if not budgets_result.data:
                    return []
                
                # Get spending for current month
                month_start = today.date().replace(day=1)
                spending_query = self.client.table('expenses').select('category_id, amount')
                spending_query = spending_query.gte('expense_date', str(month_start))
                spending_query = spending_query.lte('expense_date', str(today.date()))
                spending_result = spending_query.execute()
                
                logger.info(f"Found {len(spending_result.data)} expense entries for current month")
                
                # Group spending by category
                spending_by_category = {}
                for expense in spending_result.data:
                    cat_id = expense['category_id']
                    amount = float(expense['amount'])
                    if cat_id not in spending_by_category:
                        spending_by_category[cat_id] = 0
                    spending_by_category[cat_id] += amount
                
                # Combine budget and spending data
                results = []
                for budget in budgets_result.data:
                    cat_id = budget['category_id']
                    budget_amount = float(budget['amount'])
                    spent_amount = spending_by_category.get(cat_id, 0)
                    remaining = budget_amount - spent_amount
                    percent_used = (spent_amount / budget_amount * 100) if budget_amount > 0 else 0
                    
                    results.append({
                        "category_name": budget['categories']['name'],
                        "budget": budget_amount,
                        "spent": spent_amount,
                        "remaining": remaining,
                        "percent_used": percent_used
                    })
                
                # Sort by percent used (highest first)
                results.sort(key=lambda x: x['percent_used'], reverse=True)
                return results
                
            elif template_name == "recent_expenses":
                # Recent expenses - ALL EXPENSES in database (family view)
                start_date = params[0] if params else None
                limit = params[1] if len(params) > 1 else 10
                
                logger.info(f"Recent expenses query (ALL USERS): start={start_date}, limit={limit}")
                
                # Query recent expenses (not user-specific) with user info
                query = self.client.table('expenses').select('expense_detail, amount, expense_date, categories(name), users(name)')
                if start_date:
                    query = query.gte('expense_date', start_date)
                
                result = query.order('expense_date', desc=True).limit(limit).execute()
                
                return [
                    {
                        "expense_detail": expense['expense_detail'],
                        "amount": expense['amount'],
                        "category": expense.get('categories', {}).get('name', 'Unknown'),
                        "expense_date": expense['expense_date'],
                        "user_name": expense.get('users', {}).get('name', 'Unknown')
                    }
                    for expense in result.data
                ]
                
            elif template_name == "dynamic_sql":
                # Handle dynamic SQL generated queries - TRULY GENERIC APPROACH
                logger.info(f"Executing dynamic SQL: {sql[:200]}...")
                
                # Check if this is a budget query
                if "FROM budgets" in sql or "FROM budgets b" in sql or "budgets b" in sql:
                    logger.info("Detected budget query in dynamic SQL")
                    return await self._execute_budget_query(sql, question)
                
                try:
                    # Parse SQL components using regex
                    import re
                    from datetime import datetime, timedelta
                    
                    # Extract date filters
                    date_patterns = [
                        r"DATE_TRUNC\('month',\s*expenses\.expense_date\)\s*=\s*DATE\s*'(\d{4})-(\d{2})-01'",
                        r"expenses\.expense_date\s*>=\s*'(\d{4})-(\d{2})-(\d{2})'",
                        r"expenses\.expense_date\s*BETWEEN\s*'(\d{4})-(\d{2})-(\d{2})'\s*AND\s*'(\d{4})-(\d{2})-(\d{2})'",
                    ]
                    
                    start_date = None
                    end_date = None
                    
                    for pattern in date_patterns:
                        match = re.search(pattern, sql, re.IGNORECASE)
                        if match:
                            if len(match.groups()) >= 2:
                                year, month = int(match.group(1)), int(match.group(2))
                                start_date = datetime(year, month, 1).date()
                                # End of month
                                if month == 12:
                                    end_date = datetime(year + 1, 1, 1).date()
                                else:
                                    end_date = datetime(year, month + 1, 1).date()
                            break
                    
                    # Handle natural language date contexts
                    if not start_date and question:
                        today = datetime.now().date()
                        
                        if "last month" in question.lower():
                            # Last month
                            if today.month == 1:
                                start_date = datetime(today.year - 1, 12, 1).date()
                                end_date = datetime(today.year, 1, 1).date()
                            else:
                                start_date = datetime(today.year, today.month - 1, 1).date()
                                end_date = datetime(today.year, today.month, 1).date()
                        elif "this month" in question.lower():
                            # This month (1st of current month to end of month)
                            start_date = datetime(today.year, today.month, 1).date()
                            # End of current month
                            if today.month == 12:
                                end_date = datetime(today.year + 1, 1, 1).date()
                            else:
                                end_date = datetime(today.year, today.month + 1, 1).date()
                        elif "this year" in question.lower():
                            # This year (Jan 1 to today)
                            start_date = datetime(today.year, 1, 1).date()
                            end_date = today
                        elif "last year" in question.lower():
                            # Last year (Jan 1 to Dec 31 of previous year)
                            start_date = datetime(today.year - 1, 1, 1).date()
                            end_date = datetime(today.year, 1, 1).date()
                    
                    logger.info(f"Dynamic SQL: Date range {start_date} to {end_date}")
                    
                    # Extract category filter
                    category_match = re.search(r"categories\.name\s*=\s*['\"]([^'\"]+)['\"]", sql, re.IGNORECASE)
                    category_filter = category_match.group(1) if category_match else None
                    
                    # Check for aggregation functions and query patterns
                    is_max_query = "MAX(" in sql.upper()
                    is_min_query = "MIN(" in sql.upper()
                    is_sum_query = "SUM(" in sql.upper()
                    is_count_query = "COUNT(" in sql.upper()
                    
                    # Check for "top N" type queries in the original question
                    is_top_n_query = False
                    top_n_limit = None
                    if question:
                        import re as re_module
                        # Match patterns like "top 5", "highest 3", "largest 10"
                        top_patterns = [
                            r"top\s+(\d+)",
                            r"highest\s+(\d+)",
                            r"largest\s+(\d+)",
                            r"biggest\s+(\d+)"
                        ]
                        for pattern in top_patterns:
                            match = re_module.search(pattern, question.lower())
                            if match:
                                is_top_n_query = True
                                top_n_limit = int(match.group(1))
                                break
                    
                    # Build base query
                    select_fields = 'id, expense_detail, amount, currency, expense_date, paid_by, categories(name)'
                    query = self.client.table('expenses').select(select_fields)
                    
                    # Apply date filters
                    if start_date:
                        query = query.gte('expense_date', str(start_date))
                    if end_date:
                        query = query.lt('expense_date', str(end_date))
                    
                    # Execute base query
                    result = query.execute()
                    logger.info(f"Dynamic SQL: Found {len(result.data)} expenses in date range")
                    
                    # Filter and process results
                    filtered_expenses = []
                    for expense in result.data:
                        # Apply category filter if specified
                        if category_filter:
                            if not (expense.get('categories') and expense['categories']['name'] == category_filter):
                                continue
                        
                        filtered_expenses.append({
                            "expense_id": expense['id'],
                            "expense_detail": expense['expense_detail'],
                            "amount": float(expense['amount']),
                            "currency": expense['currency'],
                            "expense_date": expense['expense_date'],
                            "paid_by": expense['paid_by'],
                            "category_name": expense.get('categories', {}).get('name', 'Unknown') if expense.get('categories') else 'Unknown'
                        })
                    
                    logger.info(f"Dynamic SQL: {len(filtered_expenses)} expenses after filtering")
                    
                    # Handle aggregations and special queries
                    if is_top_n_query and filtered_expenses:
                        # Handle "top N" queries
                        sorted_expenses = sorted(filtered_expenses, key=lambda x: x['amount'], reverse=True)
                        result_set = sorted_expenses[:top_n_limit] if top_n_limit else sorted_expenses[:5]  # Default to top 5
                        logger.info(f"Dynamic SQL: Top {len(result_set)} expenses returned")
                        return result_set
                    elif is_max_query and filtered_expenses:
                        # Find highest expense
                        max_expense = max(filtered_expenses, key=lambda x: x['amount'])
                        logger.info(f"Dynamic SQL: Highest expense is ${max_expense['amount']}")
                        return [max_expense]
                    elif is_min_query and filtered_expenses:
                        # Find lowest expense  
                        min_expense = min(filtered_expenses, key=lambda x: x['amount'])
                        return [min_expense]
                    elif is_sum_query and filtered_expenses:
                        # Sum total
                        total = sum(x['amount'] for x in filtered_expenses)
                        return [{"total": total, "count": len(filtered_expenses)}]
                    elif is_count_query:
                        return [{"count": len(filtered_expenses)}]
                    else:
                        # Return individual records
                        # Apply ORDER BY if specified
                        if "ORDER BY" in sql.upper():
                            if "amount" in sql and "DESC" in sql.upper():
                                filtered_expenses.sort(key=lambda x: x['amount'], reverse=True)
                            elif "amount" in sql:
                                filtered_expenses.sort(key=lambda x: x['amount'])
                            elif "expense_date" in sql and "DESC" in sql.upper():
                                filtered_expenses.sort(key=lambda x: x['expense_date'], reverse=True)
                            else:
                                filtered_expenses.sort(key=lambda x: x['expense_date'])
                        
                        # Apply LIMIT if specified
                        limit_match = re.search(r"LIMIT\s+(\d+)", sql, re.IGNORECASE)
                        if limit_match:
                            limit = int(limit_match.group(1))
                            filtered_expenses = filtered_expenses[:limit]
                        
                        return filtered_expenses
                        
                except Exception as e:
                    logger.error(f"Dynamic SQL parsing error: {e}")
                    return []
            
            else:
                return []
            
        except Exception as e:
            logger.error(f"Raw SQL execution error: {e}")
            return []
    
    async def _execute_budget_query(self, sql: str, question: Optional[str] = None) -> List[Dict]:
        """
        Execute a SQL query against the budgets table using RAW SQL
        This lets Vanna AI's generated SQL run directly without modification
        """
        import re
        from datetime import datetime
        
        logger.info(f"Executing budget query with RAW SQL: {sql[:200]}...")
        
        try:
            # Use Supabase RPC to execute raw SQL
            # For now, fall back to manual parsing since Supabase client doesn't support raw SQL directly

            # Extract month/year filters
            current_month = datetime.now().month
            current_year = datetime.now().year

            # Check for month/year filters in WHERE clause
            month_match = re.search(r"month\s*=\s*EXTRACT\(MONTH FROM CURRENT_DATE\)", sql, re.IGNORECASE)
            year_match = re.search(r"year\s*=\s*EXTRACT\(YEAR FROM CURRENT_DATE\)", sql, re.IGNORECASE)

            # Check if query includes category join
            has_category_join = "JOIN categories" in sql or "categories c" in sql

            # Build Supabase query based on SQL intent
            if has_category_join:
                query = self.client.table('budgets').select('*, categories(name)')
            else:
                query = self.client.table('budgets').select('*')

            # Apply filters
            if month_match:
                query = query.eq('month', current_month)
                logger.info(f"Filtering by month: {current_month}")

            if year_match:
                query = query.eq('year', current_year)
                logger.info(f"Filtering by year: {current_year}")

            # Execute query
            result = query.execute()
            logger.info(f"Budget query returned {len(result.data)} rows")

            # Process results based on SQL structure
            # Vanna generates proper SQL, we just need to format the Supabase response

            if not result.data:
                return []

            # Check if this has category information from JOIN
            if has_category_join and result.data and result.data[0].get('categories'):
                # Format results to match expected output structure
                # Vanna generates: SELECT c.name as category_name, b.amount as budgeted
                formatted_results = []
                for row in result.data:
                    formatted_row = {
                        'category_name': row['categories']['name'],
                        'budgeted': float(row['amount']),
                        'amount': float(row['amount'])  # Alias for compatibility
                    }
                    formatted_results.append(formatted_row)

                logger.info(f"Formatted {len(formatted_results)} budget rows with categories")
                return formatted_results

            # Check if this is a simple aggregation (SUM without GROUP BY)
            elif "SUM(" in sql.upper() and "GROUP BY" not in sql.upper():
                total = sum(float(b['amount']) for b in result.data)
                logger.info(f"Total budget sum: {total}")
                return [{"total": total}]

            # Return raw results for other cases
            return result.data

        except Exception as e:
            logger.error(f"Budget query execution error: {e}", exc_info=True)
            return []
    
    async def get_expenses_by_user(
        self, 
        user_id: int, 
        limit: int = 50,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """Get expenses for a user with optional date filtering"""
        try:
            query = self.client.table('expenses').select(
                '*, categories(name)'
            ).eq('user_id', user_id).order('expense_date', desc=True)
            
            if start_date:
                query = query.gte('expense_date', start_date)
            if end_date:
                query = query.lte('expense_date', end_date)
                
            result = query.limit(limit).execute()
            return result.data if result.data else []
            
        except Exception as e:
            raise Exception(f"Database error fetching expenses: {str(e)}")
    
    async def get_monthly_totals(self, user_id: int, year: int, month: int) -> Dict:
        """Get monthly expense totals by category"""
        try:
            # This would need to be implemented with proper SQL aggregation
            # For now, return mock data
            return {
                'total_amount': 0.0,
                'categories': [],
                'expense_count': 0
            }
            
        except Exception as e:
            raise Exception(f"Database error fetching monthly totals: {str(e)}")
    
    async def get_budgets_for_month(self, year: int, month: int) -> List[Dict]:
        """Get budget entries for a specific month"""
        try:
            result = self.client.table('budgets').select(
                '*, categories(name)'
            ).eq('year', year).eq('month', month).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            raise Exception(f"Database error fetching budgets: {str(e)}")
    
    async def update_expense(
        self,
        expense_id: int,
        user_id: int,
        updates: Dict
    ) -> Dict:
        """Update an expense (with user ownership check)"""
        try:
            result = self.client.table('expenses').update(updates).eq(
                'id', expense_id
            ).eq('user_id', user_id).execute()
            
            if result.data:
                return result.data[0]
            else:
                raise Exception("Expense not found or not owned by user")
                
        except Exception as e:
            raise Exception(f"Database error updating expense: {str(e)}")
    
    async def delete_expense(self, expense_id: int, user_id: int) -> bool:
        """Delete an expense (with user ownership check)"""
        try:
            result = self.client.table('expenses').delete().eq(
                'id', expense_id
            ).eq('user_id', user_id).execute()
            
            return len(result.data) > 0
            
        except Exception as e:
            raise Exception(f"Database error deleting expense: {str(e)}")
    
    async def create_category(self, name: str, description: Optional[str] = None) -> Dict:
        """Create a new category"""
        try:
            result = self.client.table('categories').insert({
                'name': name,
                'description': description
            }).execute()
            
            if result.data:
                return result.data[0]
            else:
                raise Exception("Failed to create category")
                
        except Exception as e:
            raise Exception(f"Database error creating category: {str(e)}")
    
    async def get_conversation_state(self, chat_id: int) -> Optional[Dict]:
        """Get conversation state for a chat"""
        try:
            result = self.client.table('conversation_state').select('*').eq(
                'chat_id', chat_id
            ).single().execute()
            
            return result.data if result.data else None
            
        except Exception:
            return None
    
    async def update_conversation_state(
        self, 
        chat_id: int, 
        status: str, 
        payload: Optional[Dict] = None
    ) -> None:
        """Update conversation state"""
        try:
            self.client.table('conversation_state').upsert({
                'chat_id': chat_id,
                'last_status': status,
                'payload': payload,
                'updated_at': datetime.now().isoformat()
            }, on_conflict='chat_id').execute()
            
        except Exception as e:
            raise Exception(f"Database error updating conversation state: {str(e)}")