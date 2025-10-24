"""
Currency conversion functionality
Handles multi-currency expense tracking with exchange rates
"""
from datetime import datetime
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)

class CurrencyConverter:
    def __init__(self, db_client):
        self.db_client = db_client
        self.supported_currencies = {'CAD', 'USD', 'MXN', 'EUR', 'GBP'}
        self.default_currency = 'MXN'
    
    def get_currency_symbol(self, currency_code: str) -> str:
        """Get currency symbol for display"""
        symbols = {
            'CAD': '$',
            'USD': '$',
            'MXN': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥'
        }
        return symbols.get(currency_code.upper(), currency_code)
    
    def normalize_currency_code(self, currency: str) -> str:
        """Normalize currency code"""
        if not currency:
            return self.default_currency
        
        currency = currency.upper().strip()
        
        # Handle common variations
        currency_mapping = {
            'DOLLAR': 'CAD',
            'DOLLARS': 'CAD', 
            'CAN': 'CAD',
            'CANADIAN': 'CAD',
            'US': 'USD',
            'AMERICAN': 'USD',
            'PESO': 'MXN',
            'PESOS': 'MXN',
            'MEXICAN': 'MXN',
            'EURO': 'EUR',
            'EUROS': 'EUR',
            'POUND': 'GBP',
            'POUNDS': 'GBP',
            'STERLING': 'GBP'
        }
        
        return currency_mapping.get(currency, currency)
    
    def is_supported_currency(self, currency_code: str) -> bool:
        """Check if currency is supported"""
        return self.normalize_currency_code(currency_code) in self.supported_currencies
    
    async def convert_amount(
        self, 
        amount: float, 
        from_currency: str, 
        to_currency: str = None
    ) -> Dict:
        """
        Convert amount between currencies
        Returns: {
            'converted_amount': float,
            'original_amount': float,
            'from_currency': str,
            'to_currency': str,
            'rate': float,
            'rate_date': str,
            'success': bool,
            'error': str (if any)
        }
        """
        try:
            from_curr = self.normalize_currency_code(from_currency)
            to_curr = self.normalize_currency_code(to_currency or self.default_currency)
            
            # If same currency, no conversion needed
            if from_curr == to_curr:
                return {
                    'converted_amount': amount,
                    'original_amount': amount,
                    'from_currency': from_curr,
                    'to_currency': to_curr,
                    'rate': 1.0,
                    'rate_date': datetime.now().isoformat(),
                    'success': True
                }
            
            # Get exchange rate from database
            rate_data = await self.db_client.get_currency_rate(from_curr, to_curr)
            
            if not rate_data:
                # Fallback to 1:1 conversion with warning
                logger.warning(f"No exchange rate found for {from_curr} to {to_curr}, using 1:1")
                return {
                    'converted_amount': amount,
                    'original_amount': amount,
                    'from_currency': from_curr,
                    'to_currency': to_curr,
                    'rate': 1.0,
                    'rate_date': None,
                    'success': False,
                    'error': 'Exchange rate not found'
                }
            
            # Calculate converted amount
            rate = rate_data['rate']
            if rate_data['direct']:
                converted_amount = amount * rate
            else:
                converted_amount = amount / rate
            
            return {
                'converted_amount': round(converted_amount, 2),
                'original_amount': amount,
                'from_currency': from_curr,
                'to_currency': to_curr,
                'rate': rate,
                'rate_date': datetime.now().isoformat(),
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Currency conversion error: {e}")
            return {
                'converted_amount': amount,
                'original_amount': amount,
                'from_currency': from_currency,
                'to_currency': to_currency or self.default_currency,
                'rate': 1.0,
                'rate_date': None,
                'success': False,
                'error': str(e)
            }
    
    async def get_supported_currencies(self) -> List[Dict]:
        """Get list of supported currencies with details"""
        currencies = []
        for code in self.supported_currencies:
            currencies.append({
                'code': code,
                'symbol': self.get_currency_symbol(code),
                'name': self._get_currency_name(code)
            })
        return currencies
    
    def _get_currency_name(self, currency_code: str) -> str:
        """Get full currency name"""
        names = {
            'CAD': 'Canadian Dollar',
            'USD': 'US Dollar',
            'MXN': 'Mexican Peso',
            'EUR': 'Euro',
            'GBP': 'British Pound'
        }
        return names.get(currency_code, currency_code)
    
    def format_amount(self, amount: float, currency: str = None) -> str:
        """Format amount with currency symbol"""
        currency = currency or self.default_currency
        symbol = self.get_currency_symbol(currency)
        
        # Format with appropriate decimal places
        if currency in ['JPY']:  # Currencies without decimals
            return f"{symbol}{amount:.0f}"
        else:
            return f"{symbol}{amount:.2f}"
    
    def parse_currency_from_text(self, text: str) -> Optional[str]:
        """Extract currency from text input"""
        if not text:
            return None
        
        text = text.upper()
        
        # Check for currency codes
        for currency in self.supported_currencies:
            if currency in text:
                return currency
        
        # Check for symbols
        symbol_mapping = {
            '$': 'CAD',  # Default to CAD for dollar symbol
            '€': 'EUR',
            '£': 'GBP',
            '¥': 'JPY'
        }
        
        for symbol, currency in symbol_mapping.items():
            if symbol in text:
                return currency
        
        return None
    
    async def update_currency_rates(self, rates_data: Dict) -> bool:
        """
        Update currency rates in database
        rates_data format: {
            'base_currency': 'MXN',
            'rates': {
                'USD': 0.74,
                'MXN': 13.5,
                'EUR': 0.68
            },
            'updated_at': '2024-01-01T00:00:00Z'
        }
        """
        try:
            base_currency = rates_data.get('base_currency', 'MXN')
            rates = rates_data.get('rates', {})
            updated_at = rates_data.get('updated_at', datetime.now().isoformat())
            
            # This would update the currency_rates table
            # Implementation depends on how the rates table is structured
            logger.info(f"Would update {len(rates)} currency rates with base {base_currency}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating currency rates: {e}")
            return False