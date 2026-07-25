import os
import logging
import requests
from flask import Flask, request, jsonify
import threading
import time
import asyncio
import aiohttp
import signal
import sys

# إعدادات التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# متغيرات عامة للتحكم في الخيوط
bot_thread = None
bot_running = False
keep_alive_thread = None
shutdown_event = threading.Event()

# معالج إيقاف التشغيل الآمن
def signal_handler(signum, frame):
    """معالج الإشارات لإيقاف التشغيل الآمن"""
    logger.info(f"📴 تم استلام إشارة {signum}، بدء إيقاف التشغيل الآمن...")
    shutdown_event.set()
    
    # إيقاف البوت
    global bot_running
    bot_running = False
    
    # انتظار انتهاء الخيوط
    if bot_thread and bot_thread.is_alive():
        logger.info("⏳ انتظار انتهاء خيط البوت...")
        bot_thread.join(timeout=10)
    
    if keep_alive_thread and keep_alive_thread.is_alive():
        logger.info("⏳ انتظار انتهاء خيط البقاء على قيد الحياة...")
        keep_alive_thread.join(timeout=5)
    
    logger.info("✅ تم إكمال إيقاف التشغيل الآمن")
    sys.exit(0)

# تسجيل معالجات الإشارات
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def async_health_check():
    """فحص صحي غير متزامن للبوت"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:10000/health", timeout=3) as response:
                if response.status == 200:
                    return True, response.status
                else:
                    return False, response.status
    except Exception as e:
        return False, str(e)

async def async_external_ping():
    """اختبار اتصال غير متزامن للخدمات الخارجية"""
    external_services = [
        "https://httpbin.org/get",
        "https://api.github.com",
        "https://www.google.com"
    ]
    
    async with aiohttp.ClientSession() as session:
        for service in external_services:
            try:
                async with session.get(service, timeout=5) as response:
                    if response.status in [200, 301, 302]:
                        return True, service
            except Exception:
                continue
    
    return False, "no_services_available"

@app.route('/')
def home():
    return jsonify({
        "status": "running",
        "bot_status": "running" if bot_running else "stopped",
        "message": "بوت الموسيقى يعمل على Render",
        "endpoints": {
            "home": "/",
            "health": "/health",
            "status": "/status",
            "bot_status": "/bot_status",
            "start_bot": "/start_bot (GET/POST)",
            "stop_bot": "/stop_bot (GET/POST)"
        }
    })

@app.route('/health')
def health():
    """نقطة فحص صحي محسّنة لـ Render"""
    try:
        # التحقق من حالة البوت
        bot_alive = bot_running and bot_thread and bot_thread.is_alive()
        
        # التحقق من حالة خيط البقاء على قيد الحياة
        keep_alive_alive = keep_alive_thread and keep_alive_thread.is_alive()
        
        # التحقق من توفر الخدمات الخارجية (بشكل متزامن لـ Render)
        external_status = {}
        external_services = [
            "https://httpbin.org/get",
            "https://api.github.com",
            "https://www.google.com"
        ]
        
        for service in external_services:
            try:
                start_time = time.time()
                response = requests.get(service, timeout=3)
                response_time = time.time() - start_time
                external_status[service] = {
                    "status": "sana",
                    "response_time": response_time,
                    "status_code": response.status_code
                }
            except Exception as e:
                external_status[service] = {
                    "status": "غير صحي",
                    "error": str(e)
                }
        
        # الحالة العامة للنظام
        overall_status = "صحي"
        if not bot_alive:
            overall_status = "متعطل جزئياً"
        if not keep_alive_alive:
            overall_status = "متعطل جزئياً"
        
        # التحقق من عدد الخدمات الخارجية الصحية
        healthy_services = sum(1 for s in external_status.values() if s.get("status") == "sana")
        if healthy_services == 0:
            overall_status = "غير صحي"
        
        # التحقق من أننا في Render
        is_render = os.environ.get('RENDER', False)
        render_info = {}
        if is_render:
            render_info = {
                "service_id": os.environ.get('RENDER_SERVICE_ID'),
                "service_url": os.environ.get('RENDER_EXTERNAL_URL'),
                "environment": os.environ.get('RENDER_ENVIRONMENT', 'production')
            }
        
        return jsonify({
            "status": overall_status,
            "timestamp": time.time(),
            "bot_status": "يعمل" if bot_alive else "متوقف",
            "bot_thread_alive": bot_thread.is_alive() if bot_thread else False,
            "keep_alive_status": "يعمل" if keep_alive_alive else "متوقف",
            "keep_alive_thread_alive": keep_alive_thread.is_alive() if keep_alive_thread else False,
            "external_services": external_status,
            "external_services_summary": {
                "total": len(external_services),
                "healthy": healthy_services,
                "unhealthy": len(external_services) - healthy_services
            },
            "uptime": time.time() - (getattr(app, '_start_time', time.time())),
            "shutdown_requested": shutdown_event.is_set(),
            "render": {
                "is_render": is_render,
                "info": render_info
            },
            "memory_usage": "غير متاح"
        })
    except Exception as e:
        logger.error(f"خطأ في الفحص الصحي: {e}")
        return jsonify({
            "status": "غير صحي",
            "error": str(e),
            "timestamp": time.time()
        }), 500

@app.route('/status')
def status():
    """اسم بديل لـ /health للتوافق"""
    return health()

@app.route('/webhook', methods=['POST'])
def webhook():
    """نقطة Webhook لـ Telegram Bot API"""
    try:
        # استلام التحديث من تيليجرام
        update = request.get_json()
        
        # تسجيل التحديث المستلم
        logger.info(f"تم استلام تحديث webhook: {update.get('update_id', 'غير معروف')}")
        
        # التحقق من حالة البوت
        logger.info(f"حالة البوت: bot_thread={bot_thread}, bot_running={bot_running}")
        
        # معالجة التحديث عبر مدير البوت
        if bot_thread and bot_running:
            try:
                # استيراد دالة معالجة تحديثات webhook
                from music_bot import process_webhook_update
                import asyncio
                
                # استخدام حلقة أحداث موجودة من خيط البوت لتسريع المعالجة
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(process_webhook_update(update))
                loop.close()
                
                logger.info(f"تم وضع التحديث {update.get('update_id', 'غير معروف')} في قائمة المعالجة")
                
            except Exception as e:
                logger.error(f"خطأ في معالجة التحديث: {e}")
                return jsonify({"status": "error", "message": f"فشل في معالجة التحديث: {str(e)}"}), 500
        else:
            logger.warning(f"البوت غير جاهز: bot_thread={bot_thread}, bot_running={bot_running}")
            # محاولة تشغيل البوت تلقائياً
            if not bot_running:
                logger.info("محاولة تشغيل البوت تلقائياً...")
                try:
                    start_bot()
                    logger.info("تم تشغيل البوت تلقائياً من webhook")
                    
                    # الآن محاولة معالجة التحديث
                    try:
                        from music_bot import process_webhook_update
                        import asyncio
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(process_webhook_update(update))
                        loop.close()
                        
                        logger.info(f"تم معالجة التحديث {update.get('update_id', 'غير معروف')} بعد التشغيل التلقائي")
                        
                    except Exception as process_error:
                        logger.error(f"فشل في معالجة التحديث بعد التشغيل التلقائي: {process_error}")
                        return jsonify({"status": "error", "message": f"تم تشغيل البوت لكن فشل في معالجة التحديث: {str(process_error)}"}), 500
                        
                except Exception as e:
                    logger.error(f"فشل في تشغيل البوت تلقائياً: {e}")
                    return jsonify({"status": "error", "message": f"فشل في تشغيل البوت: {str(e)}"}), 500
            else:
                return jsonify({"status": "error", "message": "البوت قيد التشغيل، يرجى المحاولة مرة أخرى"}), 503
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"خطأ في webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_bot_in_thread():
    """تشغيل البوت في خيط منفصل مع معالجة صحيحة للبرمجة غير المتزامنة"""
    global bot_running, shutdown_event
    
    logger.info("🚀 بدء خيط البوت...")
    try:
        # إنشاء حلقة أحداث جديدة لهذا الخيط
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("✅ تم إنشاء حلقة الأحداث لخيط البوت")
        
        # استيراد وتشغيل البوت عبر main_worker (بدون استقصاء)
        logger.info("📥 استيراد main_worker من music_bot...")
        from music_bot import main_worker
        logger.info("✅ تم استيراد main_worker بنجاح")
        
        logger.info("🚀 بدء main_worker...")
        
        # تشغيل main_worker مع معالجة إيقاف التشغيل الآمن
        try:
            loop.run_until_complete(main_worker())
        except KeyboardInterrupt:
            logger.info("📴 تم استلام إشارة مقاطعة في خيط البوت")
        except Exception as e:
            logger.error(f"❌ خطأ في main_worker: {e}")
            import traceback
            logger.error(f"تتبع الأخطاء: {traceback.format_exc()}")
        finally:
            # إيقاف تشغيل آمن للبوت
            if not shutdown_event.is_set():
                logger.info("🔄 إعادة تشغيل البوت بعد 5 ثوانٍ...")
                time.sleep(5)
                if not shutdown_event.is_set():
                    # إعادة تشغيل البوت بشكل متكرر
                    bot_thread_new = threading.Thread(target=run_bot_in_thread, daemon=True)
                    bot_thread_new.start()
                    bot_thread = bot_thread_new
                    return
        
        logger.info("✅ اكتمل main_worker")
        
    except Exception as e:
        logger.error(f"❌ خطأ في خيط البوت: {e}")
        import traceback
        logger.error(f"تتبع الأخطاء: {traceback.format_exc()}")
        
        # محاولة إعادة التشغيل عند الأخطاء الحرجة
        if not shutdown_event.is_set():
            logger.info("🔄 محاولة إعادة تشغيل البوت بعد 10 ثوانٍ...")
            time.sleep(10)
            if not shutdown_event.is_set():
                try:
                    bot_thread_new = threading.Thread(target=run_bot_in_thread, daemon=True)
                    bot_thread_new.start()
                    bot_thread = bot_thread_new
                    logger.info("✅ تم إعادة تشغيل البوت بعد خطأ حرج")
                except Exception as restart_error:
                    logger.error(f"❌ فشل في إعادة تشغيل البوت: {restart_error}")
                    bot_running = False
    finally:
        try:
            if 'loop' in locals() and loop and not loop.is_closed():
                loop.close()
                logger.info("✅ تم إغلاق حلقة الأحداث")
        except Exception as e:
            logger.error(f"❌ خطأ في إغلاق حلقة الأحداث: {e}")
        
        # تعليم البوت كغير نشط
        bot_running = False
        logger.info("📴 تم تعليم البوت كغير نشط")

@app.route('/start_bot', methods=['GET', 'POST'])
def start_bot():
    global bot_thread, bot_running
    
    if bot_running:
        return jsonify({"status": "already_running", "message": "البوت يعمل بالفعل"})
    
    try:
        # تشغيل البوت في خيط منفصل مع معالجة صحيحة للبرمجة غير المتزامنة
        bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
        bot_thread.start()
        bot_running = True
        
        logger.info("تم تشغيل البوت بنجاح")
        return jsonify({"status": "started", "message": "تم تشغيل البوت بنجاح"})
    except Exception as e:
        logger.error(f"فشل في تشغيل البوت: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/stop_bot', methods=['GET', 'POST'])
def stop_bot():
    global bot_running
    
    if not bot_running:
        return jsonify({"status": "not_running", "message": "البوت ليس قيد التشغيل"})
    
    # إيقاف البوت (تعيين العلم)
    bot_running = False
    logger.info("تم طلب إيقاف البوت")
    return jsonify({"status": "stopped", "message": "تم طلب إيقاف البوت"})

@app.route('/bot_status')
def bot_status():
    return jsonify({
        "bot_running": bot_running,
        "bot_thread_alive": bot_thread.is_alive() if bot_thread else False,
        "timestamp": time.time()
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "النقطة غير موجودة",
        "available_endpoints": {
            "home": "/",
            "health": "/health", 
            "status": "/status",
            "bot_status": "/bot_status",
            "start_bot": "/start_bot (GET/POST)",
            "stop_bot": "/stop_bot (GET/POST)"
        }
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "الطريقة غير مسموحة",
        "message": "هذه النقطة تدعم كلاً من GET و POST",
        "endpoint": request.endpoint
    }), 405

def render_keep_alive():
    """الحفاظ على النشاط بشكل قوي لـ Render - كل 30 ثانية لمنع السكون"""
    global bot_running, bot_thread, shutdown_event
    
    logger.info("🚀 تم تشغيل الحفاظ على النشاط لـ Render (كل 30 ثانية)")
    
    # عدادات للمراقبة
    ping_count = 0
    error_count = 0
    
    while not shutdown_event.is_set():
        try:
            ping_count += 1
            current_time = time.strftime("%H:%M:%S")
            
            # 1. فحص صحي بسيط
            try:
                response = requests.get("http://localhost:10000/health", timeout=3)
                if response.status_code == 200:
                    logger.info(f"💓 [{current_time}] الحفاظ على النشاط #{ping_count} - البوت نشط")
                else:
                    logger.warning(f"⚠️ [{current_time}] الفحص الصحي أعاد حالة: {response.status_code}")
            except Exception as e:
                logger.warning(f"⚠️ [{current_time}] فشل الفحص الصحي: {e}")
            
            # 2. اختبار اتصال خارجي لـ Render (يمنع السكون)
            try:
                external_services = [
                    "https://httpbin.org/get",
                    "https://api.github.com",
                    "https://www.google.com",
                    "https://www.cloudflare.com"
                ]
                
                external_success = False
                for service in external_services:
                    try:
                        response = requests.get(service, timeout=5)
                        if response.status_code in [200, 301, 302]:
                            logger.info(f"🌐 [{current_time}] اختبار الاتصال الخارجي ناجح: {service}")
                            external_success = True
                            break
                    except Exception:
                        continue
                
                if not external_success:
                    logger.warning(f"⚠️ [{current_time}] جميع اختبارات الاتصال الخارجي فشلت")
                        
            except Exception as e:
                logger.warning(f"⚠️ [{current_time}] فشل اختبار الاتصال الخارجي: {e}")
            
            # 3. التحقق من حالة البوت
            if bot_running and bot_thread and bot_thread.is_alive():
                logger.info(f"🤖 [{current_time}] البوت نشط ويعمل")
            else:
                logger.warning(f"⚠️ [{current_time}] البوت غير نشط، محاولة إعادة التشغيل")
                try:
                    # محاولة إعادة تشغيل البوت
                    bot_running = False
                    time.sleep(2)
                    
                    if not shutdown_event.is_set():
                        bot_thread_new = threading.Thread(target=run_bot_in_thread, daemon=True)
                        bot_thread_new.start()
                        bot_running = True
                        bot_thread = bot_thread_new
                        logger.info(f"🔄 [{current_time}] تم إعادة تشغيل البوت")
                    
                except Exception as restart_error:
                    logger.error(f"❌ [{current_time}] خطأ في إعادة تشغيل البوت: {restart_error}")
            
            # 4. إعادة تعيين عداد الأخطاء عند التنفيذ الناجح
            if error_count > 0:
                logger.info(f"✅ [{current_time}] إعادة تعيين عداد الأخطاء (كان: {error_count})")
                error_count = 0
            
            # 5. التحقق من إشارة الإيقاف
            if shutdown_event.is_set():
                logger.info("📴 استلم الحفاظ على النشاط إشارة الإيقاف، إنهاء العمل")
                break
            
            # 6. انتظار حتى الحفاظ التالي على النشاط - بقوة كل 30 ثانية!
            sleep_time = 30  # 30 ثانية لمنع سكون Render
            logger.info(f"⏳ [{current_time}] الحفاظ التالي على النشاط بعد {sleep_time} ثانية")
            
            # تقسيم الانتظار لأجزاء للسماح بالإنهاء السريع
            for _ in range(sleep_time):
                if shutdown_event.is_set():
                    break
                time.sleep(1)
            
        except Exception as e:
            error_count += 1
            current_time = time.strftime("%H:%M:%S")
            logger.error(f"❌ [{current_time}] خطأ في الحفاظ على النشاط #{error_count}: {e}")
            
            # عند تراكم الأخطاء، زيادة الفاصل ولكن ليس بشكل كبير
            if error_count > 5:
                logger.warning(f"⚠️ [{current_time}] أخطاء كثيرة، زيادة الفاصل إلى دقيقتين")
                for _ in range(120):  # دقيقتان
                    if shutdown_event.is_set():
                        break
                    time.sleep(1)
            else:
                for _ in range(60):  # دقيقة واحدة
                    if shutdown_event.is_set():
                        break
                    time.sleep(1)
    
    logger.info("✅ تم إنهاء الحفاظ على النشاط لـ Render")

if __name__ == '__main__':
    # تسجيل وقت بدء التطبيق
    app._start_time = time.time()
    logger.info(f"🚀 تم تشغيل التطبيق في {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # تشغيل البوت تلقائياً عند بدء التطبيق
        bot_thread = threading.Thread(target=run_bot_in_thread, daemon=True)
        bot_thread.start()
        bot_running = True
        logger.info("🤖 تم تشغيل البوت تلقائياً")
    except Exception as e:
        logger.error(f"❌ فشل في تشغيل البوت تلقائياً: {e}")
    
    # تشغيل الحفاظ على النشاط في خيط منفصل
    try:
        keep_alive_thread = threading.Thread(target=render_keep_alive, daemon=True)
        keep_alive_thread.start()
        logger.info("💓 تم تشغيل الحفاظ على النشاط تلقائياً")
    except Exception as e:
        logger.error(f"❌ فشل في تشغيل الحفاظ على النشاط تلقائياً: {e}")
    
    # تشغيل تطبيق Flask مع إعدادات محسّنة
    try:
        logger.info("🌐 تشغيل تطبيق Flask...")
        # استخدام host='0.0.0.0' للوصول من الخارج
        # استخدام port من متغيرات البيئة أو 10000 افتراضياً
        port = int(os.environ.get('PORT', 10000))
        
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,  # إيقاف التصحيح للإنتاج
            use_reloader=False,  # إيقاف إعادة التحميل لمنع التكرار
            threaded=True  # تفعيل تعدد الخيوط
        )
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل تطبيق Flask: {e}")
        # إذا لم يتم تشغيل Flask، انتظار انتهاء الخيوط الأخرى
        shutdown_event.set()
        if bot_thread and bot_thread.is_alive():
            bot_thread.join(timeout=10)
        if keep_alive_thread and keep_alive_thread.is_alive():
            keep_alive_thread.join(timeout=5)
        sys.exit(1)
