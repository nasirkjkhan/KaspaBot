import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Kaspa API endpoints
KASPA_API_BASE = "https://api.kas.fyi/v1"  # Correct API!
KASPA_EXPLORER_URL = "https://explorer.kaspa.org"

class KaspaBot:
    def __init__(self, token):
        self.token = token
        self.wallets = {}
        self.notified_transactions = {}
        self.data_file = "wallets_data.json"
        self.load_wallets()
    
    def load_wallets(self):
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.wallets = {int(k): v for k, v in data.get('wallets', {}).items()}
                    notified_data = data.get('notified_transactions', {})
                    self.notified_transactions = {k: set(v) for k, v in notified_data.items()}
                    logger.info(f"✅ Loaded {len(self.wallets)} wallets")
        except Exception as e:
            logger.error(f"Error loading: {e}")
            self.wallets = {}
            self.notified_transactions = {}
    
    def save_wallets(self):
        try:
            notified_data = {k: list(v) for k, v in self.notified_transactions.items()}
            with open(self.data_file, 'w') as f:
                json.dump({'wallets': self.wallets, 'notified_transactions': notified_data}, f)
        except Exception as e:
            logger.error(f"Error saving: {e}")
    
    def is_transaction_notified(self, wallet_address, tx_hash):
        if wallet_address not in self.notified_transactions:
            self.notified_transactions[wallet_address] = set()
        return tx_hash in self.notified_transactions[wallet_address]
    
    def mark_transaction_notified(self, wallet_address, tx_hash):
        if wallet_address not in self.notified_transactions:
            self.notified_transactions[wallet_address] = set()
        self.notified_transactions[wallet_address].add(tx_hash)
        if len(self.notified_transactions[wallet_address]) > 1000:
            sorted_txs = sorted(self.notified_transactions[wallet_address])
            self.notified_transactions[wallet_address] = set(sorted_txs[-800:])
        self.save_wallets()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [KeyboardButton("📝 Add Wallet"), KeyboardButton("📋 List Wallets")],
            [KeyboardButton("❌ Remove Wallet"), KeyboardButton("ℹ️ Help")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        welcome_message = (
            "🚀 *Welcome to Kaspa Wallet Monitor Bot!*\n\n"
            "This bot monitors your Kaspa wallet addresses and notifies you "
            "of incoming transactions.\n\n"
            "Use the buttons below to get started!"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📖 *Kaspa Wallet Monitor - Help*\n\n"
            "*Commands:*\n"
            "/start - Start the bot\n"
            "/add <address> - Add wallet address\n"
            "/list - List monitored wallets\n"
            "/remove <address> - Remove wallet\n\n"
            "*Address Format:*\n"
            "kaspa:qz7ulu4c25dh7fzec..."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def add_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if context.args and len(context.args) > 0:
            wallet_address = context.args[0].strip()
        else:
            await update.message.reply_text(
                "📝 Please provide a wallet address:\n\n"
                "Usage: /add <kaspa_address>\n"
                "Example: /add kaspa:qz7ulu4c25..."
            )
            return
        
        if not wallet_address.startswith('kaspa:'):
            await update.message.reply_text(
                "❌ Invalid address format! Must start with 'kaspa:'"
            )
            return
        
        if chat_id not in self.wallets:
            self.wallets[chat_id] = []
        
        if wallet_address in self.wallets[chat_id]:
            await update.message.reply_text(
                f"⚠️ Wallet already monitored!\n`{wallet_address}`",
                parse_mode='Markdown'
            )
            return
        
        self.wallets[chat_id].append(wallet_address)
        
        if wallet_address not in self.notified_transactions:
            self.notified_transactions[wallet_address] = set()
            await self.initialize_wallet_history(wallet_address)
        
        self.save_wallets()
        await update.message.reply_text(
            f"✅ *Wallet added successfully!*\n\n"
            f"Address: `{wallet_address}`\n\n"
            f"🔔 You'll receive notifications for NEW transactions only.",
            parse_mode='Markdown'
        )
    
    async def initialize_wallet_history(self, wallet_address):
        try:
            async with aiohttp.ClientSession() as session:
                transactions = await self.check_transactions(session, wallet_address)
                if transactions and isinstance(transactions, dict):
                    tx_list = transactions.get('transactions', [])
                    for tx in tx_list[:50]:
                        tx_hash = tx.get('transactionId', '')
                        if tx_hash:
                            self.notified_transactions[wallet_address].add(tx_hash)
                    logger.info(f"✅ Initialized {len(tx_list[:50])} existing transactions")
        except Exception as e:
            logger.error(f"Error initializing: {e}")
    
    async def list_wallets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if chat_id not in self.wallets or not self.wallets[chat_id]:
            await update.message.reply_text(
                "📭 You're not monitoring any wallets yet.\n\n"
                "Use /add <address> to start!"
            )
            return
        
        wallets_list = "📋 *Your Monitored Wallets:*\n\n"
        for idx, wallet in enumerate(self.wallets[chat_id], 1):
            short_addr = f"{wallet[:15]}...{wallet[-10:]}"
            wallets_list += f"{idx}. `{short_addr}`\n"
        wallets_list += f"\n💡 Total: {len(self.wallets[chat_id])} wallet(s)"
        await update.message.reply_text(wallets_list, parse_mode='Markdown')
    
    async def remove_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if chat_id not in self.wallets or not self.wallets[chat_id]:
            await update.message.reply_text("📭 You're not monitoring any wallets.")
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
            self.save_wallets()
            await update.message.reply_text(
                f"✅ *Wallet removed!*\n\n`{wallet_address}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Wallet not in your monitoring list.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == "📝 Add Wallet":
            await update.message.reply_text(
                "📝 *Add a Kaspa Wallet*\n\nUse: /add <kaspa_address>",
                parse_mode='Markdown'
            )
        elif text == "📋 List Wallets":
            await self.list_wallets(update, context)
        elif text == "❌ Remove Wallet":
            await update.message.reply_text(
                "❌ *Remove a Wallet*\n\nUse: /remove <kaspa_address>",
                parse_mode='Markdown'
            )
        elif text == "ℹ️ Help":
            await self.help_command(update, context)
        elif text.startswith('kaspa:'):
            context.args = [text]
            await self.add_wallet(update, context)
    
    async def check_transactions(self, session: aiohttp.ClientSession, wallet_address: str):
        try:
            # CORRECT API ENDPOINT
            url = f"{KASPA_API_BASE}/addresses/{wallet_address}/transactions"
            
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"✅ Fetched transactions for {wallet_address[:20]}...")
                    return data
                elif response.status == 404:
                    logger.warning(f"⚠️ Wallet not found: {wallet_address[:20]}...")
                    return None
                else:
                    logger.warning(f"⚠️ API status {response.status}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Timeout")
            return None
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return None
    
    async def monitor_wallets(self, application):
        logger.info("🚀 Starting wallet monitoring...")
        logger.info(f"📡 Check interval: 30 seconds")
        
        while True:
            try:
                if not self.wallets:
                    await asyncio.sleep(30)
                    continue
                
                async with aiohttp.ClientSession() as session:
                    for chat_id, wallets in list(self.wallets.items()):
                        for wallet_address in wallets:
                            logger.info(f"🔍 Checking: {wallet_address[:20]}...")
                            
                            transactions = await self.check_transactions(session, wallet_address)
                            
                            if transactions:
                                await self.process_transactions(
                                    application, chat_id, wallet_address, transactions
                                )
                            
                            await asyncio.sleep(2)
                
                logger.info("✅ Cycle complete. Waiting 30s...")
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"❌ Monitor error: {e}")
                await asyncio.sleep(60)
    
    async def process_transactions(self, application, chat_id, wallet_address, transactions):
        try:
            if not isinstance(transactions, dict):
                return
            
            tx_list = transactions.get('transactions', [])
            if not tx_list:
                logger.info(f"ℹ️ No transactions found")
                return
            
            logger.info(f"📊 Found {len(tx_list)} transactions")
            new_count = 0
            
            for tx in tx_list[:20]:
                if not isinstance(tx, dict):
                    continue
                
                tx_hash = tx.get('transactionId', '')
                if not tx_hash or self.is_transaction_notified(wallet_address, tx_hash):
                    continue
                
                logger.info(f"🆕 NEW transaction: {tx_hash[:16]}...")
                
                success = await self.send_transaction_notification(
                    application, chat_id, wallet_address, tx
                )
                
                if success:
                    self.mark_transaction_notified(wallet_address, tx_hash)
                    new_count += 1
                    await asyncio.sleep(0.5)
            
            if new_count > 0:
                logger.info(f"✅ Sent {new_count} notifications")
            else:
                logger.info(f"ℹ️ No new transactions")
                
        except Exception as e:
            logger.error(f"❌ Process error: {e}")
    
    async def send_transaction_notification(self, application, chat_id, wallet_address, transaction):
        try:
            if not isinstance(transaction, dict):
                return False
            
            tx_hash = transaction.get('transactionId', 'Unknown')
            block_time = transaction.get('blockTime', 0)
            
            inputs = transaction.get('inputs', []) or []
            outputs = transaction.get('outputs', []) or []
            
            if not outputs:
                return False
            
            # Determine direction
            is_incoming = False
            amount = 0
            from_address = "Unknown"
            to_address = "Unknown"
            
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                output_addr = output.get('address', '')
                if output_addr == wallet_address:
                    is_incoming = True
                    prev_out = output.get('previousOutput', {})
                    amount += int(prev_out.get('amount', 0))
                    to_address = wallet_address
                    if inputs and isinstance(inputs[0], dict):
                        prev = inputs[0].get('previousOutput', {})
                        from_address = prev.get('address', 'Unknown')
            
            if not is_incoming and inputs:
                for inp in inputs:
                    if not isinstance(inp, dict):
                        continue
                    prev = inp.get('previousOutput', {})
                    if prev.get('address') == wallet_address:
                        from_address = wallet_address
                        if outputs and isinstance(outputs[0], dict):
                            to_address = outputs[0].get('address', 'Unknown')
                            for out in outputs:
                                if isinstance(out, dict):
                                    prev_out = out.get('previousOutput', {})
                                    amount += int(prev_out.get('amount', 0))
                        break
            
            # Convert from sompi to KAS
            amount_kas = amount / 100_000_000
            
            # Format timestamp
            tx_time = datetime.fromtimestamp(block_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
            
            explorer_link = f"{KASPA_EXPLORER_URL}/txs/{tx_hash}"
            
            from_short = f"{from_address[:15]}...{from_address[-10:]}" if len(from_address) > 30 else from_address
            to_short = f"{to_address[:15]}...{to_address[-10:]}" if len(to_address) > 30 else to_address
            tx_short = f"{tx_hash[:16]}..."
            
            direction = "📥 Incoming" if is_incoming else "📤 Outgoing"
            message = (
                f"🔔 *{direction} Transaction!*\n\n"
                f"💰 *Amount:* `{amount_kas:.8f}` KAS\n"
                f"⏰ *Time:* {tx_time}\n"
                f"📤 *From:* `{from_short}`\n"
                f"📥 *To:* `{to_short}`\n"
                f"🔗 *TX:* `{tx_short}`\n\n"
                f"[View on Explorer]({explorer_link})"
            )
            
            await application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            
            logger.info(f"✅ Sent notification to chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Notification error: {e}")
            return False

async def post_init(application):
    asyncio.create_task(bot_instance.monitor_wallets(application))

bot_instance = None

def main():
    global bot_instance
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        return
    
    logger.info("=" * 60)
    logger.info("🚀 Kaspa Wallet Monitor Bot Starting...")
    logger.info("=" * 60)
    
    bot_instance = KaspaBot(TOKEN)
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", bot_instance.start))
    application.add_handler(CommandHandler("help", bot_instance.help_command))
    application.add_handler(CommandHandler("add", bot_instance.add_wallet))
    application.add_handler(CommandHandler("list", bot_instance.list_wallets))
    application.add_handler(CommandHandler("remove", bot_instance.remove_wallet))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_text))
    
    logger.info("✅ Bot initialized")
    logger.info("📡 Ready to monitor")
    logger.info("=" * 60)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
