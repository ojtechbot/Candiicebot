# ============================================
# CandicePay - Advanced Banking Telegram Bot
# Python Single-File Implementation
# ============================================

import os
import sqlite3
import json
import logging
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, List, Optional, Any
import hashlib
import secrets
import base64
import io
from PIL import Image
import re

# ============================================
# CONFIGURATION LOADING
# ============================================

def load_config():
    """Load configuration from .env.local file"""
    config = {}
    try:
        with open('.env.local', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        print("⚠️  .env.local not found. Using environment variables.")
        # Fallback to environment variables
        config = {
            'BOT_TOKEN': os.getenv('BOT_TOKEN'),
            'PAYSTACK_SECRET_KEY': os.getenv('PAYSTACK_SECRET_KEY'),
            'PAYSTACK_PUBLIC_KEY': os.getenv('PAYSTACK_PUBLIC_KEY'),
            'DEEPSEEK_API_KEY': os.getenv('DEEPSEEK_API_KEY'),
            'SMTP_HOST': os.getenv('SMTP_HOST'),
            'SMTP_PORT': os.getenv('SMTP_PORT'),
            'SMTP_USER': os.getenv('SMTP_USER'),
            'SMTP_PASS': os.getenv('SMTP_PASS'),
            'SMTP_FROM_EMAIL': os.getenv('SMTP_FROM_EMAIL'),
            'SMTP_FROM_NAME': os.getenv('SMTP_FROM_NAME'),
            'ADMIN_USERNAME': os.getenv('ADMIN_USERNAME', 'admin'),
            'ADMIN_PASSWORD': os.getenv('ADMIN_PASSWORD', 'admin123'),
            'JWT_SECRET': os.getenv('JWT_SECRET', secrets.token_hex(32)),
            'DOMAIN_URL': os.getenv('DOMAIN_URL', 'http://localhost:3000'),
            'PORT': os.getenv('PORT', '3000')
        }
    return config

CONFIG = load_config()

# ============================================
# DATABASE SETUP
# ============================================

class Database:
    """SQLite database handler"""
    
    def __init__(self):
        self.db_path = 'candicepay.db'
        self.conn = None
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        cursor = self.conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT,
                phone TEXT,
                account_number TEXT UNIQUE,
                bank_name TEXT,
                bank_code TEXT,
                customer_code TEXT UNIQUE,
                affiliate_code TEXT UNIQUE,
                referred_by TEXT,
                wallet_balance REAL DEFAULT 0,
                total_earnings REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                kyc_verified BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL DEFAULT 0,
                net_amount REAL NOT NULL,
                recipient_name TEXT,
                recipient_account TEXT,
                recipient_bank TEXT,
                sender_name TEXT,
                sender_account TEXT,
                reference TEXT UNIQUE NOT NULL,
                paystack_reference TEXT,
                status TEXT NOT NULL,
                description TEXT,
                metadata TEXT,
                affiliate_bonus REAL DEFAULT 0,
                affiliate_user_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (affiliate_user_id) REFERENCES users(id)
            )
        ''')
        
        # Banks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS banks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL,
                slug TEXT,
                country TEXT DEFAULT 'nigeria',
                currency TEXT DEFAULT 'NGN',
                type TEXT,
                supports_transfer BOOLEAN DEFAULT 1,
                supports_virtual_account BOOLEAN DEFAULT 1,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Referrals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER UNIQUE NOT NULL,
                affiliate_code TEXT NOT NULL,
                earnings REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(id),
                FOREIGN KEY (referred_id) REFERENCES users(id)
            )
        ''')
        
        # Admin users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT DEFAULT 'admin',
                permissions TEXT DEFAULT 'all',
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Virtual accounts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS virtual_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                account_number TEXT UNIQUE NOT NULL,
                account_name TEXT NOT NULL,
                bank_name TEXT NOT NULL,
                bank_code TEXT NOT NULL,
                customer_code TEXT UNIQUE NOT NULL,
                currency TEXT DEFAULT 'NGN',
                status TEXT DEFAULT 'active',
                assigned BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Create default admin if not exists
        password_hash = hashlib.sha256(
            f"{CONFIG['ADMIN_PASSWORD']}{CONFIG['JWT_SECRET']}".encode()
        ).hexdigest()
        
        cursor.execute('''
            INSERT OR IGNORE INTO admin_users 
            (username, password_hash, email, role) 
            VALUES (?, ?, ?, ?)
        ''', (
            CONFIG['ADMIN_USERNAME'],
            password_hash,
            'admin@candicepay.com',
            'superadmin'
        ))
        
        self.conn.commit()
        print("✅ Database initialized successfully")
    
    def execute(self, query, params=()):
        """Execute a query and return cursor"""
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        self.conn.commit()
        return cursor
    
    def fetch_one(self, query, params=()):
        """Fetch a single row"""
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()
    
    def fetch_all(self, query, params=()):
        """Fetch all rows"""
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()
    
    def get_user_by_telegram_id(self, telegram_id):
        """Get user by Telegram ID"""
        return self.fetch_one(
            'SELECT * FROM users WHERE telegram_id = ?',
            (telegram_id,)
        )
    
    def create_user(self, user_data):
        """Create a new user"""
        cursor = self.execute('''
            INSERT INTO users (
                telegram_id, email, first_name, last_name, phone,
                account_number, bank_name, bank_code, customer_code,
                affiliate_code, referred_by, wallet_balance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_data['telegram_id'],
            user_data['email'],
            user_data['first_name'],
            user_data.get('last_name', ''),
            user_data.get('phone', ''),
            user_data.get('account_number', ''),
            user_data.get('bank_name', ''),
            user_data.get('bank_code', ''),
            user_data.get('customer_code', ''),
            user_data.get('affiliate_code', ''),
            user_data.get('referred_by'),
            user_data.get('wallet_balance', 0)
        ))
        
        user_id = cursor.lastrowid
        
        # Create virtual account record
        if user_data.get('account_number'):
            self.execute('''
                INSERT INTO virtual_accounts (
                    user_id, account_number, account_name, bank_name,
                    bank_code, customer_code
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                user_data['account_number'],
                f"{user_data['first_name']} {user_data.get('last_name', '')}".strip(),
                user_data.get('bank_name', ''),
                user_data.get('bank_code', ''),
                user_data.get('customer_code', '')
            ))
        
        return user_id
    
    def update_wallet(self, user_id, amount, operation='add'):
        """Update user wallet balance"""
        if operation == 'add':
            query = 'UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ?'
        else:
            query = 'UPDATE users SET wallet_balance = wallet_balance - ? WHERE id = ?'
        
        self.execute(query, (amount, user_id))
    
    def create_transaction(self, transaction_data):
        """Create a transaction record"""
        cursor = self.execute('''
            INSERT INTO transactions (
                user_id, type, amount, fee, net_amount,
                recipient_name, recipient_account, recipient_bank,
                reference, paystack_reference, status, description,
                metadata, affiliate_bonus, affiliate_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            transaction_data['user_id'],
            transaction_data['type'],
            transaction_data['amount'],
            transaction_data.get('fee', 0),
            transaction_data.get('net_amount', transaction_data['amount']),
            transaction_data.get('recipient_name'),
            transaction_data.get('recipient_account'),
            transaction_data.get('recipient_bank'),
            transaction_data['reference'],
            transaction_data.get('paystack_reference'),
            transaction_data['status'],
            transaction_data.get('description'),
            json.dumps(transaction_data.get('metadata', {})),
            transaction_data.get('affiliate_bonus', 0),
            transaction_data.get('affiliate_user_id')
        ))
        
        return cursor.lastrowid
    
    def get_transaction_stats(self):
        """Get transaction statistics"""
        return self.fetch_all('''
            SELECT 
                COUNT(*) as total_transactions,
                SUM(amount) as total_volume,
                SUM(fee) as total_fees,
                COUNT(DISTINCT user_id) as active_users,
                DATE(created_at) as date,
                type
            FROM transactions
            WHERE created_at >= DATE('now', '-30 days')
            GROUP BY DATE(created_at), type
            ORDER BY date DESC
        ''')
    
    def verify_admin(self, username, password):
        """Verify admin credentials"""
        admin = self.fetch_one(
            'SELECT * FROM admin_users WHERE username = ?',
            (username,)
        )
        
        if not admin:
            return None
        
        password_hash = hashlib.sha256(
            f"{password}{CONFIG['JWT_SECRET']}".encode()
        ).hexdigest()
        
        if admin['password_hash'] == password_hash:
            return dict(admin)
        return None
    
    def update_admin_login(self, admin_id):
        """Update admin last login time"""
        self.execute(
            'UPDATE admin_users SET last_login = CURRENT_TIMESTAMP WHERE id = ?',
            (admin_id,)
        )

# Initialize database
db = Database()

# ============================================
# PAYSTACK SERVICE
# ============================================

class PaystackService:
    """Paystack API integration"""
    
    def __init__(self):
        self.secret_key = CONFIG['PAYSTACK_SECRET_KEY']
        self.public_key = CONFIG['PAYSTACK_PUBLIC_KEY']
        self.base_url = 'https://api.paystack.co'
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
    
    async def create_customer(self, email, first_name, last_name='', phone=''):
        """Create a Paystack customer"""
        async with aiohttp.ClientSession() as session:
            data = {
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
                'phone': phone
            }
            
            async with session.post(
                f'{self.base_url}/customer',
                headers=self.headers,
                json=data
            ) as response:
                result = await response.json()
                return result
    
    async def create_virtual_account(self, customer_code, preferred_bank='wema-bank'):
        """Create a dedicated virtual account"""
        async with aiohttp.ClientSession() as session:
            data = {
                'customer': customer_code,
                'preferred_bank': preferred_bank
            }
            
            async with session.post(
                f'{self.base_url}/dedicated_account',
                headers=self.headers,
                json=data
            ) as response:
                result = await response.json()
                return result
    
    async def get_banks(self, country='nigeria'):
        """Get list of Nigerian banks"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/bank?country={country}',
                headers=self.headers
            ) as response:
                result = await response.json()
                return result
    
    async def resolve_account(self, account_number, bank_code):
        """Resolve bank account details"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/bank/resolve?account_number={account_number}&bank_code={bank_code}',
                headers=self.headers
            ) as response:
                result = await response.json()
                return result
    
    async def create_transfer_recipient(self, name, account_number, bank_code):
        """Create transfer recipient"""
        async with aiohttp.ClientSession() as session:
            data = {
                'type': 'nuban',
                'name': name,
                'account_number': account_number,
                'bank_code': bank_code,
                'currency': 'NGN'
            }
            
            async with session.post(
                f'{self.base_url}/transferrecipient',
                headers=self.headers,
                json=data
            ) as response:
                result = await response.json()
                return result
    
    async def initiate_transfer(self, amount, recipient_code, reason=''):
        """Initiate transfer to recipient"""
        async with aiohttp.ClientSession() as session:
            data = {
                'source': 'balance',
                'amount': int(amount * 100),  # Convert to kobo
                'recipient': recipient_code,
                'reason': reason
            }
            
            async with session.post(
                f'{self.base_url}/transfer',
                headers=self.headers,
                json=data
            ) as response:
                result = await response.json()
                return result
    
    async def verify_transaction(self, reference):
        """Verify transaction status"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/transaction/verify/{reference}',
                headers=self.headers
            ) as response:
                result = await response.json()
                return result
    
    async def get_balance(self):
        """Get Paystack balance"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'{self.base_url}/balance',
                headers=self.headers
            ) as response:
                result = await response.json()
                return result

# Initialize Paystack service
paystack = PaystackService()

# ============================================
# DEEPSEEK AI SERVICE
# ============================================

class DeepSeekService:
    """DeepSeek AI image processing"""
    
    def __init__(self):
        self.api_key = CONFIG['DEEPSEEK_API_KEY']
        self.base_url = 'https://api.deepseek.com/v1'
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    async def extract_bank_details(self, image_url):
        """Extract bank details from image using DeepSeek Vision"""
        async with aiohttp.ClientSession() as session:
            data = {
                'model': 'deepseek-chat',
                'messages': [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': 'Extract bank details from this image. Return JSON with: account_number, account_name, bank_name, amount. If not clear, return null values.'
                            },
                            {
                                'type': 'image_url',
                                'image_url': {'url': image_url}
                            }
                        ]
                    }
                ],
                'max_tokens': 500
            }
            
            async with session.post(
                f'{self.base_url}/chat/completions',
                headers=self.headers,
                json=data
            ) as response:
                result = await response.json()
                
                try:
                    content = result['choices'][0]['message']['content']
                    # Extract JSON from response
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        extracted = json.loads(json_match.group())
                        return {
                            'success': True,
                            'data': extracted
                        }
                except (KeyError, json.JSONDecodeError) as e:
                    pass
                
                return {
                    'success': False,
                    'error': 'Could not extract bank details'
                }

# Initialize DeepSeek service
deepseek = DeepSeekService()

# ============================================
# EMAIL SERVICE
# ============================================

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

class EmailService:
    """Email service for transaction receipts"""
    
    def __init__(self):
        self.smtp_host = CONFIG['SMTP_HOST']
        self.smtp_port = int(CONFIG['SMTP_PORT'])
        self.smtp_user = CONFIG['SMTP_USER']
        self.smtp_pass = CONFIG['SMTP_PASS']
        self.from_email = CONFIG['SMTP_FROM_EMAIL']
        self.from_name = CONFIG['SMTP_FROM_NAME']
    
    def send_transaction_email(self, to_email, transaction):
        """Send transaction receipt email"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"CandicePay - Transaction {transaction['status'].title()}"
            msg['From'] = formataddr((self.from_name, self.from_email))
            msg['To'] = to_email
            
            # Create HTML content
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #4CAF50; color: white; padding: 20px; text-align: center; }}
                    .content {{ background: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
                    .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 10px; background: white; }}
                    .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>CandicePay</h1>
                        <h2>Transaction Receipt</h2>
                    </div>
                    <div class="content">
                        <div class="detail-row">
                            <span>Reference:</span>
                            <span><strong>{transaction['reference']}</strong></span>
                        </div>
                        <div class="detail-row">
                            <span>Amount:</span>
                            <span><strong>₦{transaction['amount']:,.2f}</strong></span>
                        </div>
                        <div class="detail-row">
                            <span>Recipient:</span>
                            <span>{transaction.get('recipient_name', 'N/A')}</span>
                        </div>
                        <div class="detail-row">
                            <span>Status:</span>
                            <span>{transaction['status'].upper()}</span>
                        </div>
                        <div class="detail-row">
                            <span>Date:</span>
                            <span>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>
                        </div>
                        <p>Thank you for using CandicePay!</p>
                    </div>
                    <div class="footer">
                        <p>Need help? Contact {self.from_email}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Attach HTML
            msg.attach(MIMEText(html, 'html'))
            
            # Send email
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            
            print(f"✅ Email sent to {to_email}")
            return True
            
        except Exception as e:
            print(f"❌ Email sending failed: {e}")
            return False
    
    def send_welcome_email(self, to_email, user_details):
        """Send welcome email to new user"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = 'Welcome to CandicePay!'
            msg['From'] = formataddr((self.from_name, self.from_email))
            msg['To'] = to_email
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <body>
                <h2>Welcome to CandicePay, {user_details['first_name']}!</h2>
                <p>Your virtual account has been created:</p>
                <p><strong>Account Number:</strong> {user_details['account_number']}</p>
                <p><strong>Bank:</strong> {user_details['bank_name']}</p>
                <p>Start banking with us today!</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html'))
            
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
            
            return True
            
        except Exception as e:
            print(f"Welcome email failed: {e}")
            return False

# Initialize email service
email_service = EmailService()

# ============================================
# TELEGRAM BOT
# ============================================

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes
)

class CandicePayBot:
    """Main Telegram bot class"""
    
    def __init__(self):
        self.bot_token = CONFIG['BOT_TOKEN']
        self.application = None
        self.user_states = {}  # Store user conversation states
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Check for referral code
        referral_code = None
        if context.args and len(context.args) > 0:
            referral_code = context.args[0]
        
        # Check if user exists
        existing_user = db.get_user_by_telegram_id(user.id)
        
        if existing_user:
            # Existing user
            keyboard = [
                [KeyboardButton("💰 Make Payment"), KeyboardButton("📊 Check Balance")],
                [KeyboardButton("📋 Transaction History"), KeyboardButton("👥 Affiliate")],
                [KeyboardButton("🏦 Supported Banks"), KeyboardButton("🆘 Support")]
            ]
            
            await update.message.reply_text(
                f"👋 Welcome back, {existing_user['first_name']}!\n\n"
                f"*Account:* {existing_user['account_number']}\n"
                f"*Balance:* ₦{existing_user['wallet_balance']:,.2f}\n"
                f"*Status:* {existing_user['status']}\n\n"
                "Use the buttons below to get started!",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
        else:
            # New user
            if referral_code:
                self.user_states[user.id] = {
                    'step': 'awaiting_registration',
                    'referred_by': referral_code
                }
            else:
                self.user_states[user.id] = {'step': 'awaiting_registration'}
            
            keyboard = [
                [KeyboardButton("📝 Register Account")],
                [KeyboardButton("ℹ️ Learn More"), KeyboardButton("🆘 Support")]
            ]
            
            await update.message.reply_text(
                "🎉 *Welcome to CandicePay!*\n\n"
                "Your smart banking assistant with:\n"
                "✅ Instant Nigerian bank transfers\n"
                "✅ Virtual account generation\n"
                "✅ Smart image payment processing\n"
                "✅ 0.5% affiliate rewards\n"
                "✅ Email transaction receipts\n\n"
                "Tap 'Register Account' to get started!",
                parse_mode='Markdown',
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
    
    async def register(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle registration"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        existing_user = db.get_user_by_telegram_id(user.id)
        
        if existing_user:
            await update.message.reply_text(
                f"✅ You're already registered!\n\n"
                f"*Account Details:*\n"
                f"🏦 Bank: {existing_user['bank_name']}\n"
                f"📱 Account: {existing_user['account_number']}\n"
                f"💰 Balance: ₦{existing_user['wallet_balance']:,.2f}\n\n"
                f"Use /pay to make transfers.",
                parse_mode='Markdown'
            )
            return
        
        # Start registration process
        self.user_states[user.id] = {'step': 'awaiting_email'}
        await update.message.reply_text(
            "📝 *Account Registration*\n\n"
            "Let's create your banking account. Please send your email address:",
            parse_mode='Markdown'
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages during registration"""
        user = update.effective_user
        text = update.message.text
        
        if user.id not in self.user_states:
            return
        
        state = self.user_states[user.id]
        
        try:
            if state['step'] == 'awaiting_email':
                # Validate email
                if '@' not in text or '.' not in text:
                    await update.message.reply_text("Please enter a valid email address:")
                    return
                
                state['email'] = text
                state['step'] = 'awaiting_first_name'
                self.user_states[user.id] = state
                
                await update.message.reply_text("Great! Now send your first name:")
            
            elif state['step'] == 'awaiting_first_name':
                state['first_name'] = text
                state['step'] = 'awaiting_phone'
                self.user_states[user.id] = state
                
                await update.message.reply_text("Send your phone number (e.g., 08012345678):")
            
            elif state['step'] == 'awaiting_phone':
                # Basic phone validation
                phone = ''.join(filter(str.isdigit, text))
                if len(phone) < 10:
                    await update.message.reply_text("Please enter a valid phone number (10+ digits):")
                    return
                
                state['phone'] = phone
                self.user_states[user.id] = state
                
                # Start account creation
                await update.message.reply_text("🔄 Creating your virtual account...")
                
                # Generate affiliate code
                affiliate_code = f"CANDICE{secrets.token_hex(3).upper()}"
                
                # Create Paystack customer
                customer_result = await paystack.create_customer(
                    email=state['email'],
                    first_name=state['first_name'],
                    phone=state['phone']
                )
                
                if not customer_result.get('status'):
                    raise Exception("Paystack customer creation failed")
                
                customer_code = customer_result['data']['customer_code']
                
                # Create virtual account
                va_result = await paystack.create_virtual_account(customer_code)
                
                if not va_result.get('status'):
                    raise Exception("Virtual account creation failed")
                
                account_data = va_result['data']
                
                # Save user to database
                user_id = db.create_user({
                    'telegram_id': user.id,
                    'email': state['email'],
                    'first_name': state['first_name'],
                    'phone': state['phone'],
                    'account_number': account_data['account_number'],
                    'bank_name': account_data['bank']['name'],
                    'bank_code': account_data['bank']['code'],
                    'customer_code': customer_code,
                    'affiliate_code': affiliate_code,
                    'referred_by': state.get('referred_by')
                })
                
                # Clear state
                del self.user_states[user.id]
                
                # Send success message
                keyboard = [
                    [KeyboardButton("💰 Make Payment"), KeyboardButton("📊 Check Balance")],
                    [KeyboardButton("📋 Transaction History"), KeyboardButton("👥 Affiliate")],
                    [KeyboardButton("🏦 Supported Banks"), KeyboardButton("🆘 Support")]
                ]
                
                await update.message.reply_text(
                    f"🎉 *Registration Successful!*\n\n"
                    f"*Your Virtual Account:*\n"
                    f"🏦 Bank: {account_data['bank']['name']}\n"
                    f"📱 Account Number: *{account_data['account_number']}*\n"
                    f"👤 Account Name: {state['first_name']}\n\n"
                    f"*How to use:*\n"
                    f"1. Send money to the account above\n"
                    f"2. Funds appear in your wallet instantly\n"
                    f"3. Make payments to any Nigerian bank\n\n"
                    f"*Affiliate Code:* {affiliate_code}\n"
                    f"Share to earn 0.5% on referrals!",
                    parse_mode='Markdown',
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                
                # Send welcome email
                email_service.send_welcome_email(state['email'], {
                    'first_name': state['first_name'],
                    'account_number': account_data['account_number'],
                    'bank_name': account_data['bank']['name']
                })
                
                # Handle referral if applicable
                if state.get('referred_by'):
                    referrer = db.fetch_one(
                        'SELECT * FROM users WHERE affiliate_code = ?',
                        (state['referred_by'],)
                    )
                    if referrer:
                        db.execute('''
                            INSERT INTO referrals (referrer_id, referred_id, affiliate_code)
                            VALUES (?, ?, ?)
                        ''', (referrer['id'], user_id, state['referred_by']))
                        
                        # Notify referrer
                        await context.bot.send_message(
                            referrer['telegram_id'],
                            f"🎊 New Referral!\n\n"
                            f"{state['first_name']} just joined using your code!\n"
                            f"You'll earn 0.5% on all their transactions."
                        )
        
        except Exception as e:
            print(f"Registration error: {e}")
            await update.message.reply_text(
                "❌ Registration failed. Please try again with /register"
            )
            if user.id in self.user_states:
                del self.user_states[user.id]
    
    async def pay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle payment command"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        existing_user = db.get_user_by_telegram_id(user.id)
        
        if not existing_user:
            await update.message.reply_text(
                "Please register first using /register to start banking with us."
            )
            return
        
        balance = existing_user['wallet_balance'] or 0
        
        if balance <= 0:
            await update.message.reply_text(
                f"❌ Insufficient balance\n\n"
                f"Your wallet balance: ₦{balance:,.2f}\n"
                f"Please deposit to your virtual account:\n"
                f"🏦 Bank: {existing_user['bank_name']}\n"
                f"📱 Account: *{existing_user['account_number']}*\n\n"
                f"Funds appear instantly after deposit.",
                parse_mode='Markdown'
            )
            return
        
        # Start payment flow
        self.user_states[user.id] = {
            'step': 'awaiting_payment_method',
            'user_id': existing_user['id'],
            'balance': balance
        }
        
        keyboard = [
            [
                InlineKeyboardButton("📸 Scan Bank Slip", callback_data='payment_scan'),
                InlineKeyboardButton("📝 Enter Manually", callback_data='payment_manual')
            ],
            [
                InlineKeyboardButton("💳 Saved Beneficiaries", callback_data='payment_saved')
            ]
        ]
        
        await update.message.reply_text(
            f"💸 *Make a Payment*\n\n"
            f"*Available Balance:* ₦{balance:,.2f}\n\n"
            f"Choose payment method:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo uploads for payment scanning"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        if user.id not in self.user_states:
            return
        
        state = self.user_states[user.id]
        if state['step'] != 'awaiting_payment_scan':
            return
        
        try:
            await update.message.reply_text("🔍 Processing image...")
            
            # Get the largest photo
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            file_url = file.file_path
            
            # Use DeepSeek to extract bank details
            result = await deepseek.extract_bank_details(file_url)
            
            if not result['success']:
                await update.message.reply_text(
                    "❌ Could not read bank details from the image.\n"
                    "Please ensure:\n"
                    "• Clear photo of bank slip or check\n"
                    "• Account number is visible\n"
                    "• Bank name is visible\n\n"
                    "Try again or use manual entry."
                )
                return
            
            details = result['data']
            state['payment_details'] = details
            state['step'] = 'awaiting_payment_confirmation'
            self.user_states[user.id] = state
            
            # Check if amount is specified
            if not details.get('amount') or details['amount'] <= 0:
                state['step'] = 'awaiting_payment_amount'
                self.user_states[user.id] = state
                
                await update.message.reply_text(
                    f"✅ *Details Extracted:*\n\n"
                    f"👤 Account Name: {details['account_name']}\n"
                    f"📱 Account Number: {details['account_number']}\n"
                    f"🏦 Bank: {details['bank_name']}\n\n"
                    f"Please enter the amount to send:",
                    parse_mode='Markdown'
                )
                return
            
            # Show confirmation with amount
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Confirm Payment", 
                        callback_data=f"confirm_payment_{details['amount']}"
                    ),
                    InlineKeyboardButton("❌ Cancel", callback_data='cancel_payment')
                ]
            ]
            
            await update.message.reply_text(
                f"✅ *Details Extracted:*\n\n"
                f"👤 Account Name: {details['account_name']}\n"
                f"📱 Account Number: {details['account_number']}\n"
                f"🏦 Bank: {details['bank_name']}\n"
                f"💰 Amount: ₦{details['amount']:,.2f}\n\n"
                f"Confirm payment?",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            print(f"Photo processing error: {e}")
            await update.message.reply_text(
                "❌ Error processing image. Please try again."
            )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards"""
        query = update.callback_query
        user = query.from_user
        data = query.data
        
        await query.answer()
        
        try:
            if data == 'payment_scan':
                self.user_states[user.id] = {
                    **self.user_states.get(user.id, {}),
                    'step': 'awaiting_payment_scan'
                }
                await query.edit_message_text(
                    "📸 Send a clear photo of the bank slip or check.\n"
                    "Make sure account details are visible."
                )
            
            elif data.startswith('confirm_payment_'):
                amount = float(data.replace('confirm_payment_', ''))
                state = self.user_states.get(user.id, {})
                
                if not state or 'payment_details' not in state:
                    await query.edit_message_text("❌ Payment details not found. Please start over.")
                    return
                
                state['payment_details']['amount'] = amount
                
                await query.edit_message_text("🔄 Processing payment...")
                
                # Process payment
                payment_result = await self.process_payment(
                    user.id, 
                    state['payment_details'],
                    state.get('user_id')
                )
                
                if payment_result['success']:
                    await query.edit_message_text(
                        f"✅ *Payment Initiated!*\n\n"
                        f"Amount: ₦{amount:,.2f}\n"
                        f"To: {state['payment_details']['account_name']}\n"
                        f"Reference: {payment_result['reference']}\n\n"
                        f"Status will update shortly. Receipt sent to your email.",
                        parse_mode='Markdown'
                    )
                    
                    # Clear state
                    if user.id in self.user_states:
                        del self.user_states[user.id]
                else:
                    await query.edit_message_text(
                        f"❌ Payment failed: {payment_result['error']}\n\n"
                        f"Please try again or contact support."
                    )
        
        except Exception as e:
            print(f"Callback error: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again.")
    
    async def process_payment(self, telegram_id, payment_details, user_id=None):
        """Process a payment"""
        try:
            if not user_id:
                user = db.get_user_by_telegram_id(telegram_id)
                if not user:
                    return {'success': False, 'error': 'User not found'}
                user_id = user['id']
            
            # Get bank code
            banks_result = await paystack.get_banks()
            if not banks_result.get('status'):
                return {'success': False, 'error': 'Could not fetch banks'}
            
            banks = banks_result['data']
            bank = None
            for b in banks:
                if (payment_details['bank_name'].lower() in b['name'].lower() or 
                    b['name'].lower() in payment_details['bank_name'].lower()):
                    bank = b
                    break
            
            if not bank:
                return {'success': False, 'error': 'Bank not found'}
            
            # Resolve account
            resolve_result = await paystack.resolve_account(
                payment_details['account_number'],
                bank['code']
            )
            
            if not resolve_result.get('status'):
                return {'success': False, 'error': 'Account verification failed'}
            
            # Create transfer recipient
            recipient_result = await paystack.create_transfer_recipient(
                name=payment_details['account_name'],
                account_number=payment_details['account_number'],
                bank_code=bank['code']
            )
            
            if not recipient_result.get('status'):
                return {'success': False, 'error': 'Recipient creation failed'}
            
            recipient_code = recipient_result['data']['recipient_code']
            
            # Initiate transfer
            transfer_result = await paystack.initiate_transfer(
                amount=payment_details['amount'],
                recipient_code=recipient_code,
                reason='Payment via CandicePay'
            )
            
            if not transfer_result.get('status'):
                return {'success': False, 'error': 'Transfer initiation failed'}
            
            transfer_data = transfer_result['data']
            
            # Update user wallet
            db.update_wallet(user_id, payment_details['amount'], 'subtract')
            
            # Calculate affiliate bonus (0.5%)
            affiliate_bonus = payment_details['amount'] * 0.005
            affiliate_user_id = None
            
            user = db.fetch_one('SELECT * FROM users WHERE id = ?', (user_id,))
            if user and user['referred_by']:
                referrer = db.fetch_one(
                    'SELECT * FROM users WHERE affiliate_code = ?',
                    (user['referred_by'],)
                )
                if referrer:
                    affiliate_user_id = referrer['id']
                    db.update_wallet(referrer['id'], affiliate_bonus, 'add')
            
            # Create transaction record
            reference = f"CANDICE-{int(datetime.now().timestamp())}-{secrets.token_hex(4).upper()}"
            
            transaction_id = db.create_transaction({
                'user_id': user_id,
                'type': 'payment',
                'amount': payment_details['amount'],
                'net_amount': payment_details['amount'],
                'recipient_name': payment_details['account_name'],
                'recipient_account': payment_details['account_number'],
                'recipient_bank': payment_details['bank_name'],
                'reference': reference,
                'paystack_reference': transfer_data.get('reference'),
                'status': 'pending',
                'description': 'Smart image payment',
                'affiliate_bonus': affiliate_bonus,
                'affiliate_user_id': affiliate_user_id
            })
            
            # Send email receipt
            user_email = user['email'] if user else ''
            if user_email:
                email_service.send_transaction_email(user_email, {
                    'reference': reference,
                    'amount': payment_details['amount'],
                    'recipient_name': payment_details['account_name'],
                    'status': 'pending'
                })
            
            return {
                'success': True,
                'reference': reference,
                'transaction_id': transaction_id
            }
            
        except Exception as e:
            print(f"Payment processing error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check balance"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        existing_user = db.get_user_by_telegram_id(user.id)
        
        if not existing_user:
            await update.message.reply_text("Please register first using /register")
            return
        
        # Get recent transactions
        transactions = db.fetch_all(
            'SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
            (existing_user['id'],)
        )
        
        transaction_list = ''
        if transactions:
            transaction_list = '\n*Recent Transactions:*\n'
            for t in transactions:
                amount = t['amount']
                sign = '+' if t['type'] == 'deposit' else '-'
                transaction_list += f"• {sign}₦{abs(amount):,.2f} - {t['status']}\n"
        
        keyboard = [
            [
                InlineKeyboardButton("💸 Make Payment", callback_data='quick_payment'),
                InlineKeyboardButton("📥 Deposit", callback_data='deposit_funds')
            ],
            [
                InlineKeyboardButton("📋 Full History", callback_data='full_history'),
                InlineKeyboardButton("👥 Affiliate", callback_data='affiliate_dashboard')
            ]
        ]
        
        await update.message.reply_text(
            f"💰 *Account Balance*\n\n"
            f"*Available:* ₦{existing_user['wallet_balance'] or 0:,.2f}\n"
            f"*Account:* {existing_user['account_number']}\n"
            f"*Bank:* {existing_user['bank_name']}\n"
            f"*Status:* {existing_user['status']}\n"
            f"{transaction_list}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def affiliate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show affiliate program"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        existing_user = db.get_user_by_telegram_id(user.id)
        
        if not existing_user:
            await update.message.reply_text("Please register first using /register")
            return
        
        # Get affiliate stats
        referrals = db.fetch_all(
            'SELECT COUNT(*) as count, SUM(earnings) as total_earnings FROM referrals WHERE referrer_id = ?',
            (existing_user['id'],)
        )
        
        stats = referrals[0] if referrals else {'count': 0, 'total_earnings': 0}
        
        keyboard = [
            [
                InlineKeyboardButton("📤 Share My Code", callback_data='share_affiliate'),
                InlineKeyboardButton("💰 Withdraw Earnings", callback_data='withdraw_affiliate')
            ],
            [
                InlineKeyboardButton("📊 Detailed Stats", callback_data='affiliate_stats')
            ]
        ]
        
        await update.message.reply_text(
            f"👥 *Affiliate Program*\n\n"
            f"*Your Code:* `{existing_user['affiliate_code']}`\n"
            f"*Total Referrals:* {stats['count']}\n"
            f"*Total Earnings:* ₦{stats['total_earnings'] or 0:,.2f}\n"
            f"*Available Balance:* ₦{existing_user['total_earnings'] or 0:,.2f}\n\n"
            f"*How it works:*\n"
            f"• Share your code with friends\n"
            f"• They register using your link\n"
            f"• You earn *0.5%* of all their transactions\n"
            f"• Withdraw anytime to your wallet\n\n"
            f"*Share Link:*\n`https://t.me/{context.bot.username}?start={existing_user['affiliate_code']}`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def banks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show supported banks"""
        chat_id = update.effective_chat.id
        
        try:
            banks_result = await paystack.get_banks()
            
            if banks_result.get('status'):
                banks = banks_result['data']
                popular_banks = [b for b in banks if b['slug'] in [
                    'access-bank', 'first-bank', 'gtbank', 'zenith-bank', 
                    'uba', 'fidelity-bank', 'polaris-bank'
                ]]
                
                bank_list = '*Popular Banks:*\n'
                for bank in popular_banks[:10]:  # Show top 10
                    bank_list += f"• {bank['name']}\n"
                
                bank_list += f"\n*Total Supported Banks:* {len(banks)}\n"
                bank_list += "All Nigerian banks are supported for transfers."
                
                await update.message.reply_text(bank_list, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Could not fetch bank list.")
        
        except Exception as e:
            print(f"Banks command error: {e}")
            await update.message.reply_text("❌ Could not fetch bank list.")
    
    async def admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin commands"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Check if user is admin (telegram ID check)
        admin_ids = [7967638943]  # Add your Telegram ID here
        
        if user.id not in admin_ids:
            await update.message.reply_text("❌ Access denied.")
            return
        
        # Get stats
        user_count = db.fetch_one('SELECT COUNT(*) as count FROM users')
        transaction_count = db.fetch_one('SELECT COUNT(*) as count FROM transactions')
        total_volume = db.fetch_one('SELECT SUM(amount) as total FROM transactions')
        
        keyboard = [
            [
                InlineKeyboardButton("📊 System Stats", callback_data='admin_stats'),
                InlineKeyboardButton("👥 View Users", callback_data='admin_users')
            ],
            [
                InlineKeyboardButton("💰 View Transactions", callback_data='admin_transactions'),
                InlineKeyboardButton("🔔 Send Broadcast", callback_data='admin_broadcast')
            ],
            [
                InlineKeyboardButton(
                    "🌐 Web Dashboard", 
                    url=f"{CONFIG['DOMAIN_URL']}/admin"
                )
            ]
        ]
        
        await update.message.reply_text(
            f"👑 *Admin Dashboard*\n\n"
            f"*Users:* {user_count['count']}\n"
            f"*Transactions:* {transaction_count['count']}\n"
            f"*Total Volume:* ₦{total_volume['total'] or 0:,.2f}\n"
            f"*Bot Status:* ✅ Online\n\n"
            f"Web Dashboard: {CONFIG['DOMAIN_URL']}/admin",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    def setup_handlers(self):
        """Setup bot handlers"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("register", self.register))
        self.application.add_handler(CommandHandler("pay", self.pay))
        self.application.add_handler(CommandHandler("balance", self.balance))
        self.application.add_handler(CommandHandler("affiliate", self.affiliate))
        self.application.add_handler(CommandHandler("banks", self.banks))
        self.application.add_handler(CommandHandler("admin", self.admin))
        
        # Message handlers
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        # Photo handler
        self.application.add_handler(MessageHandler(
            filters.PHOTO, 
            self.handle_photo
        ))
        
        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(
            self.handle_callback
        ))
    
    async def run(self):
        """Run the bot"""
        self.application = Application.builder().token(self.bot_token).build()
        self.setup_handlers()
        
        print("🤖 CandicePay Bot starting...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        print(f"✅ Bot is running!")
        print(f"🌐 Web Dashboard: {CONFIG['DOMAIN_URL']}/admin")
        
        # Keep running
        await asyncio.Event().wait()

# ============================================
# WEB DASHBOARD (FastAPI)
# ============================================

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import jwt
from datetime import datetime, timedelta

app = FastAPI(title="CandicePay Admin Dashboard")
templates = Jinja2Templates(directory="templates")

# Create templates directory if it doesn't exist
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

def create_jwt_token(username: str, user_id: int):
    """Create JWT token for authentication"""
    payload = {
        'sub': username,
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, CONFIG['JWT_SECRET'], algorithm='HS256')

def verify_jwt_token(token: str):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, CONFIG['JWT_SECRET'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Simple session management
sessions = {}

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Admin dashboard page"""
    token = request.cookies.get("auth_token")
    if not token or not verify_jwt_token(token):
        return templates.TemplateResponse("login.html", {"request": request})
    
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/admin/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login"""
    admin = db.verify_admin(username, password)
    
    if not admin:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Invalid credentials"}
        )
    
    # Update last login
    db.update_admin_login(admin['id'])
    
    # Create token
    token = create_jwt_token(username, admin['id'])
    
    # Store session
    session_id = secrets.token_hex(16)
    sessions[session_id] = {
        'admin_id': admin['id'],
        'username': username,
        'login_time': datetime.now()
    }
    
    response = JSONResponse({"success": True})
    response.set_cookie(key="auth_token", value=token, httponly=True)
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    
    return response

@app.get("/admin/logout")
async def logout(request: Request):
    """Handle logout"""
    session_id = request.cookies.get("session_id")
    if session_id in sessions:
        del sessions[session_id]
    
    response = JSONResponse({"success": True})
    response.delete_cookie("auth_token")
    response.delete_cookie("session_id")
    return response

@app.get("/admin/api/stats")
async def get_stats(request: Request):
    """Get system statistics"""
    token = request.cookies.get("auth_token")
    if not token or not verify_jwt_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user_count = db.fetch_one('SELECT COUNT(*) as count FROM users')
    transaction_count = db.fetch_one('SELECT COUNT(*) as count FROM transactions')
    total_volume = db.fetch_one('SELECT SUM(amount) as total FROM transactions')
    today_volume = db.fetch_one('''
        SELECT SUM(amount) as total FROM transactions 
        WHERE DATE(created_at) = DATE('now')
    ''')
    
    return {
        "success": True,
        "data": {
            "users": user_count['count'],
            "transactions": transaction_count['count'],
            "totalVolume": total_volume['total'] or 0,
            "todayVolume": today_volume['total'] or 0
        }
    }

@app.get("/admin/api/users")
async def get_users(request: Request, page: int = 1, limit: int = 20, search: str = ""):
    """Get users with pagination"""
    token = request.cookies.get("auth_token")
    if not token or not verify_jwt_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    offset = (page - 1) * limit
    
    query = 'SELECT * FROM users'
    count_query = 'SELECT COUNT(*) as total FROM users'
    params = []
    
    if search:
        query += ' WHERE email LIKE ? OR first_name LIKE ? OR account_number LIKE ?'
        count_query += ' WHERE email LIKE ? OR first_name LIKE ? OR account_number LIKE ?'
        search_term = f"%{search}%"
        params = [search_term, search_term, search_term]
    
    query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    users = db.fetch_all(query, params)
    total = db.fetch_one(count_query, params[:-2])
    
    return {
        "success": True,
        "data": [dict(user) for user in users],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total['total'],
            "pages": (total['total'] + limit - 1) // limit
        }
    }

@app.get("/admin/api/transactions")
async def get_transactions(
    request: Request, 
    page: int = 1, 
    limit: int = 50, 
    type: str = "", 
    status: str = ""
):
    """Get transactions with pagination"""
    token = request.cookies.get("auth_token")
    if not token or not verify_jwt_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    offset = (page - 1) * limit
    
    query = '''
        SELECT t.*, u.first_name, u.last_name, u.email 
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
    '''
    
    count_query = 'SELECT COUNT(*) as total FROM transactions'
    params = []
    conditions = []
    
    if type:
        conditions.append('t.type = ?')
        params.append(type)
    
    if status:
        conditions.append('t.status = ?')
        params.append(status)
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
        count_query += ' WHERE ' + ' AND '.join(conditions)
    
    query += ' ORDER BY t.created_at DESC LIMIT ? OFFSET ?'
    params.extend([limit, offset])
    
    transactions = db.fetch_all(query, params)
    total = db.fetch_one(count_query, params[:-2])
    
    return {
        "success": True,
        "data": [dict(t) for t in transactions],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total['total'],
            "pages": (total['total'] + limit - 1) // limit
        }
    }

@app.post("/admin/api/broadcast")
async def broadcast_message(request: Request):
    """Send broadcast message to all users"""
    token = request.cookies.get("auth_token")
    if not token or not verify_jwt_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        data = await request.json()
        message = data.get('message', '')
        
        if not message or len(message) < 5:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Message too short"}
            )
        
        # Get all active users
        users = db.fetch_all('SELECT telegram_id FROM users WHERE status = "active"')
        
        # Note: In a real implementation, you would send messages via Telegram Bot API
        # This is a simplified version
        
        return {
            "success": True,
            "message": f"Broadcast would be sent to {len(users)} users"
        }
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ============================================
# HTML TEMPLATES
# ============================================

# Create login.html template
login_html = """
<!DOCTYPE html>
<html>
<head>
    <title>CandicePay - Admin Login</title>
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: Arial, sans-serif;
        }
        .login-card {
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        .login-header {
            text-align: center;
            margin-bottom: 2rem;
        }
        .login-header h2 {
            color: #333;
            margin-bottom: 0.5rem;
        }
        .login-header p {
            color: #666;
        }
        .form-group {
            margin-bottom: 1rem;
        }
        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            color: #555;
            font-weight: bold;
        }
        .form-group input {
            width: 100%;
            padding: 0.75rem;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 1rem;
        }
        .btn-login {
            width: 100%;
            padding: 0.75rem;
            background: #4e73df;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.3s;
        }
        .btn-login:hover {
            background: #2e59d9;
        }
        .alert {
            padding: 0.75rem;
            border-radius: 5px;
            margin-bottom: 1rem;
            display: none;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="login-header">
            <h2>CandicePay</h2>
            <p>Admin Dashboard Login</p>
        </div>
        
        <div id="alert" class="alert alert-error"></div>
        
        <form id="loginForm">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn-login">Login</button>
        </form>
    </div>
    
    <script>
        document.getElementById('loginForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const alertDiv = document.getElementById('alert');
            
            // Hide previous alerts
            alertDiv.style.display = 'none';
            
            try {
                const response = await fetch('/admin/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: new URLSearchParams({ username, password })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    window.location.href = '/admin';
                } else {
                    alertDiv.textContent = data.error || 'Login failed';
                    alertDiv.style.display = 'block';
                }
            } catch (error) {
                alertDiv.textContent = 'Network error. Please try again.';
                alertDiv.style.display = 'block';
            }
        });
    </script>
</body>
</html>
"""

# Create dashboard.html template
dashboard_html = """
<!DOCTYPE html>
<html>
<head>
    <title>CandicePay Admin Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: white;
            padding: 1rem 2rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 {
            margin: 0;
            color: #333;
        }
        .logout-btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 5px;
            cursor: pointer;
            text-decoration: none;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: white;
            padding: 1.5rem;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            margin: 0 0 0.5rem 0;
            color: #666;
            font-size: 0.9rem;
            text-transform: uppercase;
        }
        .stat-card .value {
            font-size: 2rem;
            font-weight: bold;
            color: #333;
        }
        .table-container {
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: bold;
            color: #333;
        }
        .nav-tabs {
            display: flex;
            background: white;
            border-radius: 10px 10px 0 0;
            overflow: hidden;
        }
        .nav-tab {
            padding: 1rem 1.5rem;
            background: #f8f9fa;
            border: none;
            cursor: pointer;
            flex: 1;
            text-align: center;
        }
        .nav-tab.active {
            background: white;
            font-weight: bold;
            border-bottom: 3px solid #4e73df;
        }
        .tab-content {
            display: none;
            padding: 1.5rem;
        }
        .tab-content.active {
            display: block;
        }
        .loading {
            text-align: center;
            padding: 2rem;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>CandicePay Admin Dashboard</h1>
        <button class="logout-btn" onclick="logout()">Logout</button>
    </div>
    
    <div class="nav-tabs">
        <button class="nav-tab active" onclick="switchTab('dashboard')">Dashboard</button>
        <button class="nav-tab" onclick="switchTab('users')">Users</button>
        <button class="nav-tab" onclick="switchTab('transactions')">Transactions</button>
        <button class="nav-tab" onclick="switchTab('broadcast')">Broadcast</button>
    </div>
    
    <!-- Dashboard Tab -->
    <div id="dashboard-tab" class="tab-content active">
        <div class="stats-grid" id="statsGrid">
            <div class="loading">Loading statistics...</div>
        </div>
        
        <div class="table-container">
            <h2 style="padding: 1rem; margin: 0;">Recent Transactions</h2>
            <div id="recentTransactions">
                <div class="loading">Loading transactions...</div>
            </div>
        </div>
    </div>
    
    <!-- Users Tab -->
    <div id="users-tab" class="tab-content">
        <div class="table-container">
            <div style="padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0;">Users</h2>
                <div>
                    <input type="text" id="userSearch" placeholder="Search users..." style="padding: 0.5rem; margin-right: 0.5rem;">
                    <button onclick="loadUsers()">Search</button>
                </div>
            </div>
            <div id="usersTable">
                <div class="loading">Loading users...</div>
            </div>
            <div id="usersPagination" style="padding: 1rem; text-align: center;"></div>
        </div>
    </div>
    
    <!-- Transactions Tab -->
    <div id="transactions-tab" class="tab-content">
        <div class="table-container">
            <div style="padding: 1rem; display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin: 0;">Transactions</h2>
                <div>
                    <select id="typeFilter" style="padding: 0.5rem; margin-right: 0.5rem;">
                        <option value="">All Types</option>
                        <option value="payment">Payment</option>
                        <option value="deposit">Deposit</option>
                        <option value="withdrawal">Withdrawal</option>
                    </select>
                    <select id="statusFilter" style="padding: 0.5rem; margin-right: 0.5rem;">
                        <option value="">All Status</option>
                        <option value="pending">Pending</option>
                        <option value="success">Success</option>
                        <option value="failed">Failed</option>
                    </select>
                    <button onclick="loadTransactions()">Filter</button>
                </div>
            </div>
            <div id="transactionsTable">
                <div class="loading">Loading transactions...</div>
            </div>
            <div id="transactionsPagination" style="padding: 1rem; text-align: center;"></div>
        </div>
    </div>
    
    <!-- Broadcast Tab -->
    <div id="broadcast-tab" class="tab-content">
        <div class="table-container">
            <div style="padding: 1.5rem;">
                <h2 style="margin-top: 0;">Send Broadcast Message</h2>
                <div style="background: #e7f3ff; padding: 1rem; border-radius: 5px; margin-bottom: 1rem;">
                    This message will be sent to all active users via Telegram.
                </div>
                <textarea id="broadcastMessage" rows="6" style="width: 100%; padding: 1rem; border: 1px solid #ddd; border-radius: 5px; margin-bottom: 1rem;" placeholder="Enter your message here..."></textarea>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span id="charCount">0 characters</span>
                    <button onclick="sendBroadcast()" style="padding: 0.75rem 1.5rem; background: #4e73df; color: white; border: none; border-radius: 5px; cursor: pointer;">Send Broadcast</button>
                </div>
                <div id="broadcastResult" style="margin-top: 1rem;"></div>
            </div>
        </div>
    </div>
    
    <script>
        let currentTab = 'dashboard';
        let currentUserPage = 1;
        let currentTransactionPage = 1;
        
        function switchTab(tab) {
            // Update active tab
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            
            document.querySelector(`.nav-tab[onclick="switchTab('${tab}')"]`).classList.add('active');
            document.getElementById(`${tab}-tab`).classList.add('active');
            
            currentTab = tab;
            
            // Load tab data
            switch(tab) {
                case 'dashboard':
                    loadStats();
                    loadRecentTransactions();
                    break;
                case 'users':
                    loadUsers();
                    break;
                case 'transactions':
                    loadTransactions();
                    break;
            }
        }
        
        async function loadStats() {
            try {
                const response = await fetch('/admin/api/stats');
                const data = await response.json();
                
                if (data.success) {
                    const stats = data.data;
                    document.getElementById('statsGrid').innerHTML = `
                        <div class="stat-card">
                            <h3>Total Users</h3>
                            <div class="value">${stats.users}</div>
                        </div>
                        <div class="stat-card">
                            <h3>Total Transactions</h3>
                            <div class="value">${stats.transactions}</div>
                        </div>
                        <div class="stat-card">
                            <h3>Total Volume</h3>
                            <div class="value">₦${stats.totalVolume.toLocaleString('en-NG', {minimumFractionDigits: 2})}</div>
                        </div>
                        <div class="stat-card">
                            <h3>Today's Volume</h3>
                            <div class="value">₦${stats.todayVolume.toLocaleString('en-NG', {minimumFractionDigits: 2})}</div>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }
        
        async function loadRecentTransactions() {
            try {
                const response = await fetch('/admin/api/transactions?limit=10');
                const data = await response.json();
                
                if (data.success) {
                    let html = '<table>';
                    html += '<tr><th>ID</th><th>User</th><th>Amount</th><th>Type</th><th>Status</th><th>Date</th></tr>';
                    
                    data.data.forEach(transaction => {
                        const amount = parseFloat(transaction.amount);
                        const statusClass = transaction.status === 'success' ? 'success' : 
                                          transaction.status === 'pending' ? 'warning' : 'error';
                        
                        html += `
                            <tr>
                                <td>${transaction.id}</td>
                                <td>${transaction.first_name || 'N/A'}</td>
                                <td>₦${amount.toLocaleString('en-NG', {minimumFractionDigits: 2})}</td>
                                <td>${transaction.type}</td>
                                <td>${transaction.status}</td>
                                <td>${new Date(transaction.created_at).toLocaleDateString()}</td>
                            </tr>
                        `;
                    });
                    
                    html += '</table>';
                    document.getElementById('recentTransactions').innerHTML = html;
                }
            } catch (error) {
                console.error('Failed to load recent transactions:', error);
            }
        }
        
        async function loadUsers(page = 1) {
            try {
                currentUserPage = page;
                const search = document.getElementById('userSearch').value;
                const url = `/admin/api/users?page=${page}&limit=20${search ? '&search=' + encodeURIComponent(search) : ''}`;
                
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.success) {
                    let html = '<table>';
                    html += '<tr><th>ID</th><th>Telegram ID</th><th>Name</th><th>Email</th><th>Account</th><th>Balance</th><th>Status</th></tr>';
                    
                    data.data.forEach(user => {
                        html += `
                            <tr>
                                <td>${user.id}</td>
                                <td>${user.telegram_id}</td>
                                <td>${user.first_name} ${user.last_name || ''}</td>
                                <td>${user.email}</td>
                                <td>${user.account_number || 'N/A'}</td>
                                <td>₦${(user.wallet_balance || 0).toLocaleString('en-NG', {minimumFractionDigits: 2})}</td>
                                <td>${user.status}</td>
                            </tr>
                        `;
                    });
                    
                    html += '</table>';
                    document.getElementById('usersTable').innerHTML = html;
                    
                    // Update pagination
                    updatePagination('usersPagination', data.pagination, loadUsers);
                }
            } catch (error) {
                console.error('Failed to load users:', error);
            }
        }
        
        async function loadTransactions(page = 1) {
            try {
                currentTransactionPage = page;
                const type = document.getElementById('typeFilter').value;
                const status = document.getElementById('statusFilter').value;
                let url = `/admin/api/transactions?page=${page}&limit=50`;
                
                if (type) url += `&type=${type}`;
                if (status) url += `&status=${status}`;
                
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.success) {
                    let html = '<table>';
                    html += '<tr><th>ID</th><th>User</th><th>Amount</th><th>Type</th><th>Recipient</th><th>Status</th><th>Date</th></tr>';
                    
                    data.data.forEach(transaction => {
                        const amount = parseFloat(transaction.amount);
                        
                        html += `
                            <tr>
                                <td>${transaction.id}</td>
                                <td>${transaction.first_name || 'N/A'}</td>
                                <td>₦${amount.toLocaleString('en-NG', {minimumFractionDigits: 2})}</td>
                                <td>${transaction.type}</td>
                                <td>${transaction.recipient_name || 'N/A'}</td>
                                <td>${transaction.status}</td>
                                <td>${new Date(transaction.created_at).toLocaleDateString()}</td>
                            </tr>
                        `;
                    });
                    
                    html += '</table>';
                    document.getElementById('transactionsTable').innerHTML = html;
                    
                    // Update pagination
                    updatePagination('transactionsPagination', data.pagination, loadTransactions);
                }
            } catch (error) {
                console.error('Failed to load transactions:', error);
            }
        }
        
        function updatePagination(elementId, pagination, callback) {
            const { page, pages } = pagination;
            const paginationEl = document.getElementById(elementId);
            
            let html = '';
            
            if (page > 1) {
                html += `<button onclick="callback(${page - 1})" style="margin: 0 0.25rem;">Previous</button>`;
            }
            
            for (let i = Math.max(1, page - 2); i <= Math.min(pages, page + 2); i++) {
                if (i === page) {
                    html += `<button style="margin: 0 0.25rem; background: #4e73df; color: white;" disabled>${i}</button>`;
                } else {
                    html += `<button onclick="callback(${i})" style="margin: 0 0.25rem;">${i}</button>`;
                }
            }
            
            if (page < pages) {
                html += `<button onclick="callback(${page + 1})" style="margin: 0 0.25rem;">Next</button>`;
            }
            
            paginationEl.innerHTML = html;
        }
        
        async function sendBroadcast() {
            const message = document.getElementById('broadcastMessage').value;
            const resultDiv = document.getElementById('broadcastResult');
            
            if (!message.trim()) {
                resultDiv.innerHTML = '<div style="color: #dc3545;">Please enter a message.</div>';
                return;
            }
            
            try {
                const response = await fetch('/admin/api/broadcast', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    resultDiv.innerHTML = `<div style="color: #28a745;">${data.message}</div>`;
                    document.getElementById('broadcastMessage').value = '';
                    document.getElementById('charCount').textContent = '0 characters';
                } else {
                    resultDiv.innerHTML = `<div style="color: #dc3545;">${data.error}</div>`;
                }
            } catch (error) {
                resultDiv.innerHTML = `<div style="color: #dc3545;">Failed to send broadcast: ${error.message}</div>`;
            }
        }
        
        function logout() {
            fetch('/admin/logout').then(() => {
                window.location.href = '/admin/login';
            });
        }
        
        // Character count for broadcast
        document.getElementById('broadcastMessage').addEventListener('input', function() {
            document.getElementById('charCount').textContent = this.value.length + ' characters';
        });
        
        // Load initial data
        loadStats();
        loadRecentTransactions();
        
        // Setup search on enter for users
        document.getElementById('userSearch').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                loadUsers(1);
            }
        });
    </script>
</body>
</html>
"""

# Save HTML templates
with open("templates/login.html", "w") as f:
    f.write(login_html)

with open("templates/dashboard.html", "w") as f:
    f.write(dashboard_html)

# ============================================
# MAIN ENTRY POINT
# ============================================

import uvicorn
import threading

async def run_web_server():
    """Run the FastAPI web server"""
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=int(CONFIG['PORT']),
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    """Main entry point"""
    print("\n" + "="*50)
    print("🏦 CandicePay - Advanced Banking Telegram Bot")
    print("="*50)
    
    # Initialize services
    print("🔧 Initializing services...")
    
    # Test Paystack connection
    try:
        balance_result = await paystack.get_balance()
        if balance_result.get('status'):
            print(f"✅ Paystack connected successfully")
        else:
            print(f"⚠️  Paystack connection issue: {balance_result.get('message')}")
    except Exception as e:
        print(f"⚠️  Paystack test failed: {e}")
    
    # Test database
    user_count = db.fetch_one('SELECT COUNT(*) as count FROM users')
    print(f"✅ Database connected ({user_count['count']} users)")
    
    # Create and run bot
    bot = CandicePayBot()
    
    # Run web server in background thread
    import asyncio
    loop = asyncio.get_event_loop()
    web_task = loop.create_task(run_web_server())
    
    # Run bot
    bot_task = loop.create_task(bot.run())
    
    # Wait for both tasks
    await asyncio.gather(web_task, bot_task)

if __name__ == "__main__":
    # Create requirements.txt
    requirements = """
python-telegram-bot==20.7
aiohttp==3.9.1
fastapi==0.104.1
uvicorn==0.24.0
Pillow==10.1.0
PyJWT==2.8.0
"""
    
    with open("requirements.txt", "w") as f:
        f.write(requirements)
    
    print("📋 Created requirements.txt")
    print("\n🚀 To install dependencies:")
    print("   pip install -r requirements.txt")
    print("\n🚀 To run CandicePay:")
    print("   python candicepay.py")
    print("\n📝 Make sure to create .env.local with your configuration!")
    
    # Run the application
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down CandicePay...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
