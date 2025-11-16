"""
Expense classification system - port of the JavaScript classification logic
Handles merchant categorization using rules and fuzzy matching
"""
import re
from typing import Dict, List, Optional
from fuzzywuzzy import fuzz

class ExpenseClassifier:
    def __init__(self, db_client):
        self.db_client = db_client
        self.category_rules = self._build_category_rules()
    
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        
        # Convert to lowercase and remove accents
        normalized = str(text).lower()
        # Remove diacritics (basic approach)
        normalized = re.sub(r'[àáäâèéëêìíïîòóöôùúüûñç]', 
                          lambda m: 'aaaeeeeiiiioooouuuunc'[ord(m.group())-224], normalized)
        
        # Remove special characters and normalize spaces
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _build_category_rules(self) -> Dict[str, List[str]]:
        """Build category matching rules - sync with database categories"""
        return {
            'Rent': ['rent', 'lease', 'landlord', 'renta'],
            'Transportation': [
                'transport', 'uber', 'lyft', 'taxi', 'bus', 'metro',
                'subway', 'compass', 'evo', 'parking', 'transporte'
            ],
            'Gas': [
                'gas', 'gasolina', 'fuel', 'pemex', 'shell', 'bp'
            ],
            'Groceries': [
                'grocery', 'groceries', 'supermarket', 'super market',
                'superstore', 'super store', 'costco', 'walmart', 't&t',
                'no frills', 'real canadian superstore', 'iga', 'super',
                'supermercado', 'despensa'
            ],
            'Oxxo': [
                'oxxo', '7 eleven', '7eleven', 'seven eleven',
                'convenience store', 'corner store', 'tienda'
            ],
            'Medicines': ['medicine', 'medicines', 'pharmacy', 'drugstore', 'rx', 'msp', 'farmacia', 'medicinas'],
            'Puppies': [
                'puppy', 'puppies', 'dog', 'dogs', 'vet', 'veterinary',
                'pet', 'kenzo', 'romulo', 'perro', 'perros', 'mascota'
            ],
            'Telcom': [
                'telcom', 'telecom', 'telus', 'cellular', 'cellphone',
                'mobile', 'phone plan', 'data plan', 'internet', 'celular', 'celu'
            ],
            'Subscriptions': [
                'subscription', 'subscriptions', 'spotify', 'netflix',
                'youtube', 'icloud', 'apple care', 'google suite',
                'membership amex', 'duolingo', 'suscripcion', 'suscripciones'
            ],
            'Restaurants': [
                'restaurant', 'restaurants', 'cafe', 'coffee', 'kebab',
                'sushi', 'tacos', 'ice cream', 'pan y te', 'comida',
                'restaurante', 'desayuno', 'almuerzo', 'cena', 'breakfast', 'lunch', 'dinner'
            ],
            'Clothing': ['clothes', 'clothing', 'apparel', 'zara', 'hm', 'uniqlo', 'ropa'],
            'Travel': ['travel', 'flight', 'airline', 'hotel', 'luggage', 'viaje', 'vuelo'],
            'Entertainment': [
                'entertainment', 'movie', 'cinema', 'show', 'concert',
                'f1', 'baile', 'clase de baile', 'entretenimiento', 'cine'
            ],
            'Gadgets': [
                'gadget', 'gadgets', 'electronics', 'iphone', 'ipad',
                'macbook', 'laptop', 'electronica'
            ],
            'Home appliances': [
                'appliance', 'home appliance', 'vacuum', 'mixer',
                'pet hair remover', 'electrodomestico', 'aparato'
            ],
            'Beauty': [
                'beauty', 'belleza', 'makeup', 'maquillaje', 'cosmetics', 'cosmeticos',
                'hair', 'pelo', 'salon', 'spa', 'nail', 'uñas', 'skincare',
                'jabon', 'shampoo', 'perfume'
            ],
            'Others': ['others', 'misc', 'breka', 'networking', 'otros', 'otro', 'other', 'varios'],
            'Finance': [
                'finance', 'bank fee', 'icbc', 'amex membership',
                'examen de manejo', 'finanzas', 'banco', 'seguro', 'insurance'
            ],
            'Gym': [
                'gym', 'fitness', 'membership gym', 'clases de baile',
                'latina online gym', 'gimnasio', 'clase', 'ejercicio', 'deporte'
            ],
            'Canada': [
                'canada', 'pgwp', 'tcf', 'licencia', 'examen de manejo', 'visa', 'immigration'
            ]
        }
    
    def _score_match(self, normalized_merchant: str, phrase: str) -> float:
        """Score how well a phrase matches the merchant name"""
        if not phrase or not normalized_merchant:
            return 0.0
        
        phrase = self.normalize_text(phrase)
        
        # Exact match
        if normalized_merchant == phrase:
            return 2.0
        
        # Contains match
        if phrase in normalized_merchant:
            return min(1.5, len(phrase) / max(4, len(normalized_merchant)))
        
        # Fuzzy match
        fuzzy_score = fuzz.partial_ratio(normalized_merchant, phrase)
        if fuzzy_score > 80:
            return fuzzy_score / 100.0
        
        return 0.0
    
    async def classify_expense(self, merchant: str, categories: List[Dict], explicit_category: str = None) -> Dict:
        """
        Classify an expense by merchant name
        Args:
            merchant: The merchant/store name to classify
            categories: List of available categories from database
            explicit_category: Optional explicit category name provided by user
        Returns: {
            'category_name': str,
            'category_id': int,
            'confidence': float,
            'suggestions': List[Dict]
        }
        """
        if not merchant:
            return {'category_name': None, 'category_id': None, 'confidence': 0.0, 'suggestions': []}

        # If user explicitly specified a category, use it directly
        if explicit_category:
            normalized_category = self.normalize_text(explicit_category)
            # Try to find exact or close match in available categories
            for cat in categories:
                normalized_cat_name = self.normalize_text(cat['name'])
                # Exact match or very close match
                if normalized_cat_name == normalized_category or normalized_category in normalized_cat_name:
                    return {
                        'category_name': cat['name'],
                        'category_id': cat['id'],
                        'confidence': 2.0,  # High confidence - user specified it!
                        'suggestions': []
                    }

            # If no exact match, try fuzzy matching on category names
            best_match = None
            best_score = 0.0
            for cat in categories:
                score = self._score_match(normalized_category, cat['name'])
                if score > best_score:
                    best_score = score
                    best_match = cat

            if best_match and best_score > 0.5:
                return {
                    'category_name': best_match['name'],
                    'category_id': best_match['id'],
                    'confidence': 1.8,  # High confidence - user specified category
                    'suggestions': []
                }

        normalized_merchant = self.normalize_text(merchant)

        # Score against category rules
        category_scores = {}
        
        for category_name, phrases in self.category_rules.items():
            max_score = 0.0
            for phrase in phrases:
                score = self._score_match(normalized_merchant, phrase)
                max_score = max(max_score, score)
            
            if max_score > 0:
                category_scores[category_name] = max_score
        
        # Find best match
        best_category = None
        best_score = 0.0
        
        if category_scores:
            best_category = max(category_scores.keys(), key=lambda k: category_scores[k])
            best_score = category_scores[best_category]
        
        # Check against database categories for exact matches
        if best_score < 0.6:
            for cat in categories:
                cat_score = self._score_match(normalized_merchant, cat['name'])
                if cat_score > best_score:
                    best_category = cat['name']
                    best_score = cat_score
        
        # Find category ID
        category_id = None
        if best_category:
            category_id = self._find_category_id_by_name(best_category, categories)
        
        # Generate suggestions for low confidence matches
        suggestions = []
        if best_score < 0.7:
            suggestions = self._get_category_suggestions(normalized_merchant, categories)
        
        return {
            'category_name': best_category,
            'category_id': category_id,
            'confidence': best_score,
            'suggestions': suggestions[:6]  # Limit to top 6
        }
    
    def _find_category_id_by_name(self, name: str, categories: List[Dict]) -> Optional[int]:
        """Find category ID by name"""
        for cat in categories:
            if cat['name'].lower() == name.lower():
                return cat['id']
        return None
    
    def _get_category_suggestions(self, normalized_merchant: str, categories: List[Dict]) -> List[Dict]:
        """Get category suggestions for uncertain matches"""
        suggestions = []
        
        # Score all categories
        for cat in categories:
            # Score against category name
            name_score = self._score_match(normalized_merchant, cat['name'])
            
            # Score against category rules
            rule_score = 0.0
            if cat['name'] in self.category_rules:
                for phrase in self.category_rules[cat['name']]:
                    phrase_score = self._score_match(normalized_merchant, phrase)
                    rule_score = max(rule_score, phrase_score)
            
            total_score = max(name_score, rule_score)
            
            if total_score > 0.1:  # Minimum threshold for suggestions
                suggestions.append({
                    'id': cat['id'],
                    'name': cat['name'],
                    'score': total_score
                })
        
        # Sort by score, descending
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        return suggestions