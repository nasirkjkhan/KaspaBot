import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Kaspa Explorer API endpoint
KASPA_API_BASE = "https://api.kaspa.org"
KASPA_EXPLORER_URL = "https://explorer.kaspa.org"

class KaspaBot:
    def __init__(self, token):
        self.token = token
        self.wallets = {}  # {chat_id: [wallet_addresses]}
        self.last_checked = {}  # {wallet_address: timestamp}
        self.data_file = "wallets_data.json"
        self.load_wallets()
        
    def load_wallets(self):
        """Load saved wallet addresses from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.wallets = {int(k): v for k, v in data.get('wallets', {}).items()}
                    self.last_checked = data.get('last_checked', {})
                    logger.info(f"Loaded {len(self.wallets)} wallet configurations")
        except Exception as e:
            logger.error(f"Error loading wallets: {e}")
            self.wallets = {}
            self.last_checked = {}
    
    def save_wallets(self):
        """Save wallet addresses to file"""
        try:
            with open(self.data_file, 'w') as f:
                json.dump({
                    'wallets': self.wallets,
                    'last_checked': self.last_checked
                }, f)
            logger.info("Wallets saved successfully")
        except Exception as e:
            logger.error(f"Error saving wallets: {e}")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        keyboard = [
            [KeyboardButton("📝 Add Wallet"), KeyboardButton("📋 List Wallets")],
            [KeyboardButton("❌ Remove Wallet"), KeyboardButton("ℹ️ Help")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        welcome_message = (
            "🚀 *Welcome to Kaspa Wallet Monitor Bot!*\n\n"
            "This bot monitors your Kaspa wallet addresses and notifies you "
            "of incoming transactions.\n\n"
            "Use the buttons below to:\n"
            "• Add wallet addresses to monitor\n"
            "• View your monitored wallets\n"
            "• Remove wallets from monitoring\n\n"
            "Get started by adding a wallet address!"
        )
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command and Help button"""
        help_text = (
            "📖 *Kaspa Wallet Monitor - Help*\n\n"
            "*Commands:*\n"
            "/start - Start the bot\n"
            "/add <address> - Add a Kaspa wallet address\n"
            "/list - List all monitored wallets\n"
            "/remove <address> - Remove a wallet address\n"
            "/help - Show this help message\n\n"
            "*Wallet Address Format:*\n"
            "Kaspa addresses start with 'kaspa:' followed by the address\n"
            "Example: kaspa:qz7ulu4c25dh7fzec9zjyrmlhnkzrg4wmf89q37g3d5x3y2uzlsvg3q3x8n4m\n\n"
            "*Notifications:*\n"
            "You'll receive instant notifications when:\n"
            "• KAS tokens are received\n"
            "• Tokens are sent from your wallet\n\n"
            "Each notification includes:\n"
            "• Transaction amount\n"
            "• From/To addresses\n"
            "• Transaction hash\n"
            "• Direct link to explorer"
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def add_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle adding a wallet address"""
        chat_id = update.effective_chat.id
        
        # Check if command has argument
        if context.args and len(context.args) > 0:
            wallet_address = context.args[0].strip()
        else:
            await update.message.reply_text(
                "📝 Please provide a wallet address:\n\n"
                "Usage: /add <kaspa_address>\n"
                "Example: /add kaspa:qz7ulu4c25dh7fzec9zjyrmlhnkzrg4wmf89q37g3d5x3y2uzlsvg3q3x8n4m\n\n"
                "Or send me the wallet address directly."
            )
            return
        
        # Validate Kaspa address format
        if not wallet_address.startswith('kaspa:'):
            await update.message.reply_text(
                "❌ Invalid Kaspa address format!\n\n"
                "Kaspa addresses must start with 'kaspa:'\n"
                "Please try again with a valid address."
            )
            return
        
        # Add wallet to monitoring list
        if chat_id not in self.wallets:
            self.wallets[chat_id] = []
        
        if wallet_address in self.wallets[chat_id]:
            await update.message.reply_text(
                f"⚠️ This wallet is already being monitored!\n\n"
                f"Address: `{wallet_address}`",
                parse_mode='Markdown'
            )
            return
        
        self.wallets[chat_id].append(wallet_address)
        self.last_checked[wallet_address] = datetime.now().isoformat()
        self.save_wallets()
        
        await update.message.reply_text(
            f"✅ *Wallet added successfully!*\n\n"
            f"Address: `{wallet_address}`\n\n"
            f"You'll now receive notifications for all transactions to this address.",
            parse_mode='Markdown'
        )
    
    async def list_wallets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle listing all monitored wallets"""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.wallets or not self.wallets[chat_id]:
            await update.message.reply_text(
                "📭 You're not monitoring any wallets yet.\n\n"
                "Use /add <address> to start monitoring a wallet!"
            )
            return
        
        wallets_list = "📋 *Your Monitored Wallets:*\n\n"
        for idx, wallet in enumerate(self.wallets[chat_id], 1):
            short_addr = f"{wallet[:15]}...{wallet[-10:]}"
            wallets_list += f"{idx}. `{short_addr}`\n"
        
        wallets_list += f"\n💡 Total: {len(self.wallets[chat_id])} wallet(s)"
        
        await update.message.reply_text(wallets_list, parse_mode='Markdown')
    
    async def remove_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle removing a wallet address"""
        chat_id = update.effective_chat.id
        
        if chat_id not in self.wallets or not self.wallets[chat_id]:
            await update.message.reply_text(
                "📭 You're not monitoring any wallets."
            )
            return
        
        if not context.args or len(context.args) == 0:
            await update.message.reply_text(
                "📝 Please provide the wallet address to remove:\n\n"
                "Usage: /remove <kaspa_address>"
            )
            return
        
        wallet_address = context.args[0].strip()
        
        if wallet_address in self.wallets[chat_id]:
            self.wallets[chat_id].remove(wallet_address)
            if wallet_address in self.last_checked:
                del self.last_checked[wallet_address]
            self.save_wallets()
            
            await update.message.reply_text(
                f"✅ *Wallet removed successfully!*\n\n"
                f"Address: `{wallet_address}`\n\n"
                f"You'll no longer receive notifications for this wallet.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ This wallet is not in your monitoring list."
            )
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button presses and text messages"""
        text = update.message.text
        
        if text == "📝 Add Wallet":
            await update.message.reply_text(
                "📝 *Add a Kaspa Wallet*\n\n"
                "Send me the wallet address using:\n"
                "/add <kaspa_address>\n\n"
                "Example:\n"
                "/add kaspa:qz7ulu4c25dh7fzec9zjyrmlhnkzrg4wmf89q37g3d5x3y2uzlsvg3q3x8n4m",
                parse_mode='Markdown'
            )
        elif text == "📋 List Wallets":
            await self.list_wallets(update, context)
        elif text == "❌ Remove Wallet":
            await update.message.reply_text(
                "❌ *Remove a Wallet*\n\n"
                "Use: /remove <kaspa_address>",
                parse_mode='Markdown'
            )
        elif text == "ℹ️ Help":
            await self.help_command(update, context)
        elif text.startswith('kaspa:'):
            # Treat as add wallet command
            context.args = [text]
            await self.add_wallet(update, context)
    
    async def check_transactions(self, session: aiohttp.ClientSession, wallet_address: str):
        """Check for new transactions on a wallet"""
        try:
            # Using Kaspa API to get transactions
            # Note: Replace with actual Kaspa API endpoint
            url = f"{KASPA_API_BASE}/addresses/{wallet_address}/full-transactions"
            
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.warning(f"API returned status {response.status} for {wallet_address}")
                    return None
        except Exception as e:
            logger.error(f"Error checking transactions for {wallet_address}: {e}")
            return None
    
    async def monitor_wallets(self, application):
        """Background task to monitor all wallets"""
        logger.info("Starting wallet monitoring...")
        
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    for chat_id, wallets in self.wallets.items():
                        for wallet_address in wallets:
                            # Check for new transactions
                            transactions = await self.check_transactions(session, wallet_address)
                            
                            if transactions:
                                # Process and send notifications
                                await self.process_transactions(
                                    application, 
                                    chat_id, 
                                    wallet_address, 
                                    transactions
                                )
                            
                            # Small delay between checks
                            await asyncio.sleep(1)
                
                # Wait before next monitoring cycle (e.g., every 30 seconds)
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def process_transactions(self, application, chat_id, wallet_address, transactions):
        """Process transactions and send notifications"""
        try:
            # This is a simplified version - adapt based on actual Kaspa API response
            if isinstance(transactions, list):
                for tx in transactions[:5]:  # Limit to recent 5 transactions
                    await self.send_transaction_notification(
                        application,
                        chat_id,
                        wallet_address,
                        tx
                    )
        except Exception as e:
            logger.error(f"Error processing transactions: {e}")
    
    async def send_transaction_notification(self, application, chat_id, wallet_address, transaction):
        """Send notification for a transaction"""
        try:
            # Extract transaction details (adapt based on actual API response)
            tx_hash = transaction.get('transaction_id', 'N/A')
            
            # Simplified - you'll need to parse the actual transaction structure
            inputs = transaction.get('inputs', [])
            outputs = transaction.get('outputs', [])
            
            # Determine if incoming or outgoing
            is_incoming = any(
                output.get('script_public_key_address') == wallet_address 
                for output in outputs
            )
            
            if is_incoming:
                # Incoming transaction
                from_address = inputs[0].get('previous_outpoint_address', 'Unknown') if inputs else 'Unknown'
                to_address = wallet_address
                amount = sum(
                    output.get('amount', 0) 
                    for output in outputs 
                    if output.get('script_public_key_address') == wallet_address
                )
            else:
                # Outgoing transaction
                from_address = wallet_address
                to_address = outputs[0].get('script_public_key_address', 'Unknown') if outputs else 'Unknown'
                amount = sum(output.get('amount', 0) for output in outputs)
            
            # Convert amount from sompi to KAS (1 KAS = 100,000,000 sompi)
            amount_kas = amount / 100000000
            
            # Create explorer link
            explorer_link = f"{KASPA_EXPLORER_URL}/txs/{tx_hash}"
            
            # Format notification message
            direction = "📥 Incoming" if is_incoming else "📤 Outgoing"
            message = (
                f"🔔 *{direction} Transaction Detected!*\n\n"
                f"💰 *Amount:* {amount_kas:.8f} KAS\n"
                f"📤 *From:* `{from_address[:20]}...`\n"
                f"📥 *To:* `{to_address[:20]}...`\n"
                f"🔗 *TX Hash:* `{tx_hash[:20]}...`\n\n"
                f"[View on Explorer]({explorer_link})"
            )
            
            await application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

async def post_init(application):
    """Post initialization - start monitoring task"""
    asyncio.create_task(bot_instance.monitor_wallets(application))

# Main bot instance
bot_instance = None

def main():
    """Main function to run the bot"""
    global bot_instance
    
    # Get token from environment variable
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    # Create bot instance
    bot_instance = KaspaBot(TOKEN)
    
    # Create application
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot_instance.start))
    application.add_handler(CommandHandler("help", bot_instance.help_command))
    application.add_handler(CommandHandler("add", bot_instance.add_wallet))
    application.add_handler(CommandHandler("list", bot_instance.list_wallets))
    application.add_handler(CommandHandler("remove", bot_instance.remove_wallet))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_text))
    
    # Start bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
