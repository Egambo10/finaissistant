"""
Vanna AI Integration for FinAIssistant
Provides RAG-based Text-to-SQL generation with database-specific training
"""

import os
import logging
from typing import Optional
from vanna.openai.openai_chat import OpenAI_Chat
from vanna.chromadb.chromadb_vector import ChromaDB_VectorStore

logger = logging.getLogger(__name__)

class SupabaseVanna(ChromaDB_VectorStore, OpenAI_Chat):
    """
    Vanna AI customized for Supabase/PostgreSQL
    Combines ChromaDB vector store with OpenAI for Text-to-SQL
    """
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)


class VannaTrainer:
    """
    Handles training and SQL generation using Vanna AI
    """
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.vn = SupabaseVanna(config={
            'api_key': api_key,
            'model': model
        })
        self._is_trained = False
        logger.info("🤖 Vanna AI initialized with model: %s", model)
    
    def train_schema(self):
        """
        Train Vanna on the Supabase database schema
        This should be called once during initialization
        """
        logger.info("📚 Training Vanna on database schema...")
        
        # Train on expenses table DDL
        self.vn.train(ddl="""
            CREATE TABLE expenses (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id),
                category_id UUID NOT NULL REFERENCES categories(id),
                expense_detail TEXT NOT NULL,
                amount DECIMAL NOT NULL,
                currency VARCHAR(3) DEFAULT 'MXN',
                original_amount DECIMAL,
                original_currency VARCHAR(3),
                expense_date DATE NOT NULL DEFAULT CURRENT_DATE,
                paid_by TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            );
        """)
        
        # Train on budgets table DDL
        self.vn.train(ddl="""
            CREATE TABLE budgets (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                category_id UUID NOT NULL REFERENCES categories(id),
                amount DECIMAL NOT NULL,
                currency VARCHAR(3) DEFAULT 'MXN',
                month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
                year INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Train on categories table DDL
        self.vn.train(ddl="""
            CREATE TABLE categories (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Train on users table DDL
        self.vn.train(ddl="""
            CREATE TABLE users (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                telegram_id BIGINT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Train on currency_rates table DDL
        self.vn.train(ddl="""
            CREATE TABLE currency_rates (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                base_currency VARCHAR(3) NOT NULL,
                target_currency VARCHAR(3) NOT NULL,
                rate DECIMAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        logger.info("✅ Schema training complete")
    
    def train_documentation(self):
        """
        Train Vanna on business logic and domain knowledge
        """
        logger.info("📖 Training Vanna on documentation...")
        
        self.vn.train(documentation="""
        FinAIssistant Business Rules:
        - Default currency is MXN (Mexican Peso)
        - All amounts are stored in MXN in the 'amount' field
        - Original amounts/currencies are preserved in original_amount and original_currency fields
        - The 'month' column in budgets uses integers 1-12 (not month names)
        - The 'year' column in budgets stores the year (e.g., 2025)
        - Family expense tracking: queries should include expenses from all users
        - The 'paid_by' field is TEXT containing the user's name (not a foreign key)
        - Date functions: Use PostgreSQL date functions like DATE_TRUNC(), EXTRACT()
        - Current date: Use CURRENT_DATE or CURRENT_TIMESTAMP
        - Always use COALESCE() for NULL handling in aggregations
        """)
        
        self.vn.train(documentation="""
        Common Query Patterns:
        - For "this month": WHERE DATE_TRUNC('month', expense_date) = DATE_TRUNC('month', CURRENT_DATE)
        - For current month budget: WHERE month = EXTRACT(MONTH FROM CURRENT_DATE) AND year = EXTRACT(YEAR FROM CURRENT_DATE)
        - For totals: Use SUM() with COALESCE(SUM(amount), 0)
        - For category breakdowns: JOIN categories c ON c.id = category_id
        - For budget vs spending: Use CTEs (WITH clauses) to organize queries
        """)
        
        logger.info("✅ Documentation training complete")
    
    def train_examples(self):
        """
        Train Vanna on example question-SQL pairs
        This improves accuracy for common queries
        """
        logger.info("💡 Training Vanna on example queries...")
        
        # Total spending this month
        self.vn.train(
            question="What is my total spending this month?",
            sql="""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM expenses
                WHERE DATE_TRUNC('month', expense_date) = DATE_TRUNC('month', CURRENT_DATE)
            """
        )
        
        # Total budget this month
        self.vn.train(
            question="What is my total budget for this month?",
            sql="""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM budgets
                WHERE month = EXTRACT(MONTH FROM CURRENT_DATE)
                  AND year = EXTRACT(YEAR FROM CURRENT_DATE)
            """
        )
        
        # Spending by category this month
        self.vn.train(
            question="Show me spending by category this month",
            sql="""
                SELECT 
                    c.name as category,
                    COALESCE(SUM(e.amount), 0) as total,
                    COUNT(e.id) as count
                FROM categories c
                LEFT JOIN expenses e ON e.category_id = c.id 
                    AND DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', CURRENT_DATE)
                GROUP BY c.name, c.id
                ORDER BY total DESC
            """
        )

        # Budget vs spending (English)
        self.vn.train(
            question="How am I doing against my budget this month?",
            sql="""
                WITH current_budgets AS (
                    SELECT b.category_id, c.name as category_name, b.amount as budget_amount
                    FROM budgets b
                    JOIN categories c ON c.id = b.category_id
                    WHERE b.month = EXTRACT(MONTH FROM CURRENT_DATE)
                      AND b.year = EXTRACT(YEAR FROM CURRENT_DATE)
                ),
                current_spending AS (
                    SELECT e.category_id, SUM(e.amount) as spent_amount
                    FROM expenses e
                    WHERE DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', CURRENT_DATE)
                    GROUP BY e.category_id
                )
                SELECT
                    cb.category_name,
                    COALESCE(cb.budget_amount, 0) as budget,
                    COALESCE(cs.spent_amount, 0) as spent,
                    COALESCE(cb.budget_amount, 0) - COALESCE(cs.spent_amount, 0) as remaining,
                    CASE
                        WHEN cb.budget_amount > 0
                        THEN ROUND((COALESCE(cs.spent_amount, 0) / cb.budget_amount * 100), 1)
                        ELSE 0
                    END as percent_used
                FROM current_budgets cb
                LEFT JOIN current_spending cs ON cb.category_id = cs.category_id
                ORDER BY percent_used DESC
            """
        )

        # Budget vs spending (Spanish - same SQL as English)
        self.vn.train(
            question="Cómo voy gastos vs presupuesto este mes",
            sql="""
                WITH current_budgets AS (
                    SELECT b.category_id, c.name as category_name, b.amount as budget_amount
                    FROM budgets b
                    JOIN categories c ON c.id = b.category_id
                    WHERE b.month = EXTRACT(MONTH FROM CURRENT_DATE)
                      AND b.year = EXTRACT(YEAR FROM CURRENT_DATE)
                ),
                current_spending AS (
                    SELECT e.category_id, SUM(e.amount) as spent_amount
                    FROM expenses e
                    WHERE DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', CURRENT_DATE)
                    GROUP BY e.category_id
                )
                SELECT
                    cb.category_name,
                    COALESCE(cb.budget_amount, 0) as budget,
                    COALESCE(cs.spent_amount, 0) as spent,
                    COALESCE(cb.budget_amount, 0) - COALESCE(cs.spent_amount, 0) as remaining,
                    CASE
                        WHEN cb.budget_amount > 0
                        THEN ROUND((COALESCE(cs.spent_amount, 0) / cb.budget_amount * 100), 1)
                        ELSE 0
                    END as percent_used
                FROM current_budgets cb
                LEFT JOIN current_spending cs ON cb.category_id = cs.category_id
                ORDER BY percent_used DESC
            """
        )

        # Budget vs spending variation (Spanish)
        self.vn.train(
            question="Como voy gastos va budget este mes",
            sql="""
                WITH current_budgets AS (
                    SELECT b.category_id, c.name as category_name, b.amount as budget_amount
                    FROM budgets b
                    JOIN categories c ON c.id = b.category_id
                    WHERE b.month = EXTRACT(MONTH FROM CURRENT_DATE)
                      AND b.year = EXTRACT(YEAR FROM CURRENT_DATE)
                ),
                current_spending AS (
                    SELECT e.category_id, SUM(e.amount) as spent_amount
                    FROM expenses e
                    WHERE DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', CURRENT_DATE)
                    GROUP BY e.category_id
                )
                SELECT
                    cb.category_name,
                    COALESCE(cb.budget_amount, 0) as budget,
                    COALESCE(cs.spent_amount, 0) as spent,
                    COALESCE(cb.budget_amount, 0) - COALESCE(cs.spent_amount, 0) as remaining,
                    CASE
                        WHEN cb.budget_amount > 0
                        THEN ROUND((COALESCE(cs.spent_amount, 0) / cb.budget_amount * 100), 1)
                        ELSE 0
                    END as percent_used
                FROM current_budgets cb
                LEFT JOIN current_spending cs ON cb.category_id = cs.category_id
                ORDER BY percent_used DESC
            """
        )

        # Recent expenses
        self.vn.train(
            question="Show me my recent expenses",
            sql="""
                SELECT 
                    e.expense_detail,
                    e.amount,
                    e.currency,
                    c.name as category,
                    e.expense_date,
                    e.paid_by
                FROM expenses e
                JOIN categories c ON c.id = e.category_id
                ORDER BY e.expense_date DESC, e.timestamp DESC
                LIMIT 10
            """
        )
        
        # Top spending categories this week
        self.vn.train(
            question="What are my top spending categories this week?",
            sql="""
                SELECT 
                    c.name as category,
                    SUM(e.amount) as total,
                    COUNT(e.id) as count
                FROM expenses e
                JOIN categories c ON c.id = e.category_id
                WHERE e.expense_date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY c.name, c.id
                ORDER BY total DESC
                LIMIT 5
            """
        )
        
        # Budget by category (without spending comparison)
        self.vn.train(
            question="Show me the budget by category",
            sql="""
                SELECT 
                    c.name as category_name,
                    b.amount as budgeted
                FROM budgets b
                JOIN categories c ON c.id = b.category_id
                WHERE b.month = EXTRACT(MONTH FROM CURRENT_DATE)
                  AND b.year = EXTRACT(YEAR FROM CURRENT_DATE)
                ORDER BY b.amount DESC
            """
        )
        
        # Budget by category in Spanish
        self.vn.train(
            question="Cuál es el presupuesto por categoría para este mes",
            sql="""
                SELECT 
                    c.name as category_name,
                    b.amount as budgeted
                FROM budgets b
                JOIN categories c ON c.id = b.category_id
                WHERE b.month = EXTRACT(MONTH FROM CURRENT_DATE)
                  AND b.year = EXTRACT(YEAR FROM CURRENT_DATE)
                ORDER BY b.amount DESC
            """
        )
        
        logger.info("✅ Example query training complete")
    
    def train_all(self):
        """
        Complete training workflow
        """
        try:
            self.train_schema()
            self.train_documentation()
            self.train_examples()
            self._is_trained = True
            logger.info("🎉 Vanna training completed successfully!")
        except Exception as e:
            logger.error(f"❌ Error during Vanna training: {e}", exc_info=True)
            raise
    
    def generate_sql(self, question: str) -> str:
        """
        Generate SQL query from natural language question
        
        Args:
            question: Natural language question about expenses
            
        Returns:
            Generated SQL query string
        """
        if not self._is_trained:
            logger.warning("⚠️ Vanna not trained yet, using untrained model")
        
        try:
            logger.info(f"🔍 Generating SQL for question: {question}")
            sql = self.vn.generate_sql(question)
            logger.info(f"✅ Generated SQL: {sql}")
            return sql
        except Exception as e:
            logger.error(f"❌ Error generating SQL: {e}", exc_info=True)
            raise
    
    def ask(self, question: str) -> str:
        """
        Generate SQL and optionally execute it
        This is a convenience method that wraps generate_sql
        """
        return self.generate_sql(question)
    
    def is_trained(self) -> bool:
        """Check if Vanna has been trained"""
        return self._is_trained

