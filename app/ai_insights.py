import os
from typing import Dict, Any, Union
from groq import Groq
from dotenv import load_dotenv
from .models import Subscription

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_insights(subscription: Union[Subscription, Dict[str, Any]]) -> Dict[str, Any]:
	"""
	Generate AI insights for a subscription using Groq API.
	"""
	
	# Convert Pydantic model to dict if needed
	if hasattr(subscription, 'model_dump'):
		subscription_dict = subscription.model_dump()
	else:
		subscription_dict = subscription
	
	# Create a detailed prompt for better analysis
	prompt = f"""
	Analyze this subscription service and provide detailed insights:

	Service: {subscription_dict.get('service_name', 'Unknown')}
	Cost: ${subscription_dict.get('cost', 0)} per {subscription_dict.get('billing_cycle', 'month')}
	Notes: {subscription_dict.get('notes', 'No additional notes')}

	Please provide a comprehensive analysis in the following JSON format:

	{{
		"classification": "necessary|optional|luxury",
		"cost_analysis": {{
			"monthly_equivalent": "Calculated monthly cost",
			"annual_total": "Total annual cost", 
			"cost_per_day": "Daily cost breakdown",
			"value_assessment": "High|Medium|Low value for money"
		}},
		"alternatives": [
			{{
				"name": "Alternative service name",
				"cost": "Monthly cost in USD",
				"description": "Brief description of the alternative",
				"pros": ["List of advantages"],
				"cons": ["List of disadvantages"],
				"savings_potential": "Potential monthly savings"
			}}
		],
		"recommendations": {{
			"action": "keep|downgrade|cancel|switch|optimize",
			"reasoning": "Detailed explanation of the recommendation",
			"estimated_savings": "Potential monthly savings if recommendation is followed",
			"implementation_steps": ["Step-by-step actions to take"]
		}},
		"usage_tips": {{
			"tips": [
				"Tip 1 for optimizing usage",
				"Tip 2 for cost reduction", 
				"Tip 3 for better value"
			]
		}},
		"risk_assessment": {{
			"cancellation_impact": "What happens if you cancel",
			"downgrade_impact": "What happens if you downgrade",
			"switching_risks": "Risks of switching to alternatives"
		}}
	}}

	Consider the following factors in your analysis:
	1. Service category and typical usage patterns
	2. Cost relative to similar services
	3. Necessity based on modern lifestyle needs
	4. Available alternatives and their trade-offs
	5. Potential for optimization or cost reduction
	6. Impact of cancellation or changes

	Provide realistic, actionable advice that considers both cost and value.
	"""

	try:
		response = client.chat.completions.create(
			model="llama3-8b-8192",
			messages=[
				{
					"role": "system",
					"content": "You are a financial advisor specializing in subscription management. Provide accurate, practical advice for optimizing subscription costs while maintaining value. Always respond with valid JSON format."
				},
				{
					"role": "user",
					"content": prompt
				}
			],
			temperature=0.3,
			max_tokens=2000
		)
		
		# Extract and parse the response
		content = response.choices[0].message.content
		
		# Try to extract JSON from the response
		import json
		import re
		
		# Look for JSON in the response
		json_match = re.search(r'\{.*\}', content, re.DOTALL)
		if json_match:
			try:
				insights = json.loads(json_match.group())
				return insights
			except json.JSONDecodeError:
				pass
		
		# Fallback: create structured response from text
		return create_fallback_insights(subscription_dict, content)
		
	except Exception as e:
		print(f"Error generating AI insights: {e}")
		return create_fallback_insights(subscription_dict, "Unable to generate AI insights")


def create_fallback_insights(subscription: Dict[str, Any], ai_response: str) -> Dict[str, Any]:
	"""
	Create fallback insights when AI response parsing fails.
	"""
	service_name = subscription.get('service_name', 'Unknown').lower()
	cost = subscription.get('cost', 0)
	billing_cycle = subscription.get('billing_cycle', 'monthly')
	
	# Basic classification based on service name
	category_map = {
		'netflix': 'entertainment',
		'spotify': 'entertainment', 
		'youtube': 'entertainment',
		'prime': 'entertainment',
		'disney': 'entertainment',
		'hulu': 'entertainment',
		'office': 'productivity',
		'adobe': 'productivity',
		'github': 'productivity',
		'aws': 'utility',
		'google': 'utility',
		'microsoft': 'utility',
		'domain': 'utility',
		'hosting': 'utility',
		'vpn': 'utility',
		'gym': 'health',
		'fitness': 'health',
		'meal': 'essential',
		'food': 'essential',
		'insurance': 'essential',
		'phone': 'essential',
		'internet': 'essential',
		'electricity': 'essential',
		'water': 'essential',
		'gas': 'essential'
	}
	
	category = 'other'
	classification = 'optional'
	
	for keyword, cat in category_map.items():
		if keyword in service_name:
			category = cat
			if cat in ['essential', 'utility']:
				classification = 'necessary'
			elif cat == 'entertainment':
				classification = 'optional'
			elif cat == 'productivity':
				classification = 'necessary'
			break
	
	# Calculate costs
	monthly_cost = cost if billing_cycle == 'monthly' else cost / 12 if billing_cycle == 'yearly' else cost / 4 if billing_cycle == 'quarterly' else cost * 4
	annual_cost = monthly_cost * 12
	daily_cost = monthly_cost / 30
	
	# Generate basic alternatives
	alternatives = []
	if category == 'entertainment':
		alternatives = [
			{
				"name": "Free alternatives",
				"cost": 0,
				"description": "Use free streaming services or library resources",
				"pros": ["No cost", "Still provides entertainment"],
				"cons": ["Limited content", "May have ads"],
				"savings_potential": monthly_cost
			}
		]
	elif category == 'productivity':
		alternatives = [
			{
				"name": "Free alternatives",
				"cost": 0,
				"description": "Use free productivity tools like Google Workspace",
				"pros": ["No cost", "Good for basic needs"],
				"cons": ["Limited features", "May have storage limits"],
				"savings_potential": monthly_cost
			}
		]
	
	return {
		"classification": classification,
		"cost_analysis": {
			"monthly_equivalent": round(monthly_cost, 2),
			"annual_total": round(annual_cost, 2),
			"cost_per_day": round(daily_cost, 2),
			"value_assessment": "Medium" if monthly_cost < 20 else "High" if monthly_cost < 50 else "Low"
		},
		"alternatives": alternatives,
		"recommendations": {
			"action": "keep" if classification == 'necessary' else "optimize",
			"reasoning": f"Service is classified as {classification}",
			"estimated_savings": alternatives[0]["savings_potential"] if alternatives else 0,
			"implementation_steps": ["Review current usage", "Consider alternatives", "Monitor costs"]
		},
		"usage_tips": {
			"tips": [
				"Review usage patterns monthly",
				"Consider annual billing for discounts",
				"Look for student or family plans"
			]
		},
		"risk_assessment": {
			"cancellation_impact": "May lose access to service",
			"downgrade_impact": "May lose premium features",
			"switching_risks": "Data migration and learning curve"
		}
	}
