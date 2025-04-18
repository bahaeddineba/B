document.addEventListener('DOMContentLoaded', () => {
    const chatMessages = document.getElementById('chatMessages');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    const infoIcon = document.querySelector('.fa-info-circle');

    const voiceToggle = document.createElement('div');
    voiceToggle.innerHTML = '<i class="fas fa-volume-up" title="تشغيل/إيقاف الصوت"></i>';
    voiceToggle.classList.add('voice-toggle');
    document.querySelector('.header-icons').appendChild(voiceToggle);

    let isSoundEnabled = true;

    let userLocation;

    let map = null;
    let doctorMarkers = [];

    /**
     * @param {string} content 
     * @param {string} type 
     * @returns {HTMLElement} 
     */
    function createMessageElement(content, type) {

        const messageElement = document.createElement('div');
        messageElement.classList.add('message', `${type}-message`);
        
        const messageContent = document.createElement('div');
        messageContent.classList.add('message-content');
        
        const processedContent = content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') 
            .replace(/__(.*?)__/g, '<u>$1</u>') 
            .replace(/`(.*?)`/g, '<code>$1</code>') 
            .replace(/\n/g, '<br>'); 

        const linkifiedContent = processedContent.replace(
            /https?:\/\/[^\s]+/g, 
            (url) => `<a href="${url}" target="_blank" class="message-link">${url}</a>`
        );

        messageContent.innerHTML = linkifiedContent;

        // إنشاء عنصر الوقت
        const messageTime = document.createElement('div');
        messageTime.classList.add('message-time');
        messageTime.textContent = new Date().toLocaleTimeString('ar-EG', { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: false // استخدام تنسيق 24 ساعة
        });

        // إضافة محتوى الرسالة والوقت
        messageElement.appendChild(messageContent);
        messageElement.appendChild(messageTime);

        // إضافة زر النطق فقط لرسائل البوت
        if (type === 'bot') {
            const speakButton = document.createElement('button');
            speakButton.classList.add('speak-button');
            speakButton.innerHTML = '<i class="fas fa-volume-up"></i>';
            speakButton.addEventListener('click', () => speakMessage(content, speakButton));
            messageElement.appendChild(speakButton);
        }

        return messageElement;
    }

    // دالة نطق الرسالة باستخدام خدمة تحويل النص إلى كلام
    /**
     * نطق الرسالة باستخدام خدمة تحويل النص إلى كلام
     * @param {string} text محتوى الرسالة
     * @param {HTMLElement} button زر النطق
     */
    function speakMessage(text, button) {
        // إرسال طلب إلى الخادم لتحويل النص إلى كلام
        fetch('/text-to-speech', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text: text })
        }).then(response => response.json())
        .then(data => {
            // التحقق من نجاح إنشاء الملف الصوتي
            if (data.status === 'success') {
                const audio = new Audio(data.audio_path);
                audio.play().catch(error => {
                    console.error('خطأ في تشغيل الصوت:', error);
                    alert('حدث خطأ أثناء تشغيل الصوت. يرجى التأكد من إعدادات الصوت في المتصفح.');
                });
            } else {
                console.error('فشل في إنشاء الملف الصوتي');
                alert('تعذر إنشاء الملف الصوتي. يرجى المحاولة مرة أخرى.');
            }
        }).catch(error => {
            console.error('خطأ في الاتصال بالخادم:', error);
            alert('حدث خطأ في الاتصال بالخادم. يرجى التحقق من اتصال الإنترنت.');
        });
    }

    // دالة إضافة رسالة جديدة إلى محتوى الدردشة
    /**
     * إضافة رسالة جديدة إلى محتوى الدردشة
     * @param {string} content محتوى الرسالة
     * @param {string} type نوع الرسالة (مستخدم أو بوت)
     */
    function addMessage(content, type) {
        // إنشاء عنصر الرسالة
        const messageElement = createMessageElement(content, type);
        // إضافة الرسالة إلى محتوى الدردشة
        chatMessages.appendChild(messageElement);
        // التمرير التلقائي إلى أسفل
        chatMessages.scrollTop = chatMessages.scrollHeight;
        // تطبيق التأثير المرئي
        animateMessage(messageElement);

        // نطق الرسالة إذا كان الصوت مفعلاً
        if (type === 'bot' && isSoundEnabled) {
            speakMessage(content);
        }
    }

    // دالة إضافة تأثير حركي للرسائل
    /**
     * إضافة تأثير حركي للرسائل
     * @param {HTMLElement} messageElement عنصر الرسالة
     */
    function animateMessage(messageElement) {
        // إخفاء الرسالة مبدئياً
        messageElement.style.opacity = '0';
        messageElement.style.transform = 'translateY(20px)';
        setTimeout(() => {
            // إظهار الرسالة بتأثير انزلاق
            messageElement.style.transition = 'opacity 0.3s, transform 0.3s';
            messageElement.style.opacity = '1';
            messageElement.style.transform = 'translateY(0)';
        }, 10);
    }

    // دالة إرسال رسالة المستخدم
    /**
     * إرسال رسالة المستخدم
     */
    async function sendMessage() {
        const message = userInput.value.trim();
        
        // الإجراء الأساسي للرسالة
        if (message === '') return;

        addMessage(message, 'user');
        userInput.value = '';

        try {
            // عرض مؤشر الكتابة
            const typingIndicator = ChatEnhancer.visualEffects.typingIndicator();
            
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message: message })
            });

            // إزالة مؤشر الكتابة
            typingIndicator.remove();

            const data = await response.json();
            addMessage(data.response, 'bot');
        } catch (error) {
            console.error('Error:', error);
            addMessage('حدث خطأ أثناء إرسال الرسالة', 'bot');
        }
    }

    // دالة للملاحة إلى الطبيب مع دعم متعدد للخرائط
    function navigateToDoctor(doctorLat, doctorLng) {
        getUserLocation()
            .then(userLocation => {
                const navigationUrl = `https://www.google.com/maps/dir/?api=1&origin=${userLocation.latitude},${userLocation.longitude}&destination=${doctorLat},${doctorLng}&travelmode=driving`;
                
                // فتح خرائط جوجل مباشرة
                window.open(navigationUrl, '_blank');
            })
            .catch(error => {
                console.error('خطأ في تحديد الموقع:', error);
                alert(error.message);
            });
    }

    // جعل الدالة متاحة عالميًا
    window.navigateToDoctor = navigateToDoctor;

    // دالة لتهيئة الخريطة
    function initializeMap() {
        const mapContainer = document.getElementById('mapContainer');
        const mapElement = document.getElementById('doctorMap');
        const mapIcon = document.getElementById('mapIcon');

        // تأكد من وجود العناصر
        if (!mapContainer || !mapElement || !mapIcon) {
            console.error('أحد عناصر الخريطة مفقود');
            return;
        }

        // تبديل ظهور الخريطة
        mapIcon.addEventListener('click', () => {
            console.log('تم النقر على أيقونة الخريطة');
            mapContainer.style.display = mapContainer.style.display === 'none' ? 'block' : 'none';
            
            // إنشاء الخريطة إذا لم تكن موجودة
            if (!map) {
                createMap();
            }
            
            // إعادة الخريطة إلى العرض الأصلي
            if (map) {
                map.setView([userLocation.latitude, userLocation.longitude], 13);
                
                // إعادة وضع علامات الأطباء
                doctorMarkers.forEach(marker => marker.remove());
                doctorMarkers = [];
                fetchDoctorLocations();
            }
        });
    }

    // دالة لإنشاء الخريطة
    function createMap() {
        console.log('إنشاء الخريطة');
        
        // التأكد من تحميل Leaflet
        if (typeof L === 'undefined') {
            console.error('مكتبة Leaflet غير محملة');
            alert('حدث خطأ في تحميل الخريطة');
            return;
        }

        map = L.map('doctorMap').setView([36.7538, 3.0588], 6); // إحداثيات الجزائر العاصمة

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        // الحصول على موقع المستخدم
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    userLocation = [position.coords.latitude, position.coords.longitude];
                    console.log('تم الحصول على موقع المستخدم');

                    const userMarker = L.marker(userLocation, {icon: L.icon({
                        iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
                        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png'
                    })}).addTo(map)
                    .bindPopup('موقعك الحالي').openPopup();

                    // جلب قائمة الأطباء
                    fetchDoctorLocations();
                },
                (error) => {
                    console.error("خطأ في تحديد الموقع:", error);
                    fetchDoctorLocations();
                }
            );
        } else {
            fetchDoctorLocations();
        }
    }

function fetchDoctorLocations() {
    console.log('بدء جلب مواقع الأطباء');

    // التأكد من وجود الخريطة
    if (!map) {
        console.error('الخريطة غير مهيأة');
        alert('حدث خطأ في تحميل الخريطة. يرجى إعادة تحميل الصفحة.');
        return;
    }

    fetch('/get_doctors')
        .then(response => {
            // التحقق من استجابة الخادم
            if (!response.ok) {
                throw new Error(`خطأ في الاستجابة: ${response.status}`);
            }
            return response.json();
        })
        .then(doctors => {
            // تعيين المتغير العالمي للأطباء
            window.doctorLocations = doctors;
            console.log(`تم جلب ${doctors.length} طبيب`);

            const doctorInfoContainer = document.getElementById('doctorInfo');
            const doctorMapContainer = document.getElementById('doctorMap');

            // التأكد من وجود العناصر
            if (!doctorInfoContainer || !doctorMapContainer) {
                console.error('عناصر عرض الأطباء غير موجودة');
                alert('حدث خطأ في عرض معلومات الأطباء');
                return;
            }

            // مسح المعلومات السابقة
            doctorInfoContainer.innerHTML = '';
            
            // إزالة العلامات السابقة
            doctorMarkers.forEach(marker => map.removeLayer(marker));
            doctorMarkers = [];

            doctors.forEach(doctor => {
                // التحقق من صحة إحداثيات الطبيب
                if (!isValidCoordinate(doctor.latitude, doctor.longitude)) {
                    console.warn(`إحداثيات غير صالحة للطبيب: ${doctor.name}`);
                    return;
                }

                const marker = L.marker([doctor.latitude, doctor.longitude], {
                    icon: L.icon({
                        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
                        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
                        iconSize: [25, 41],
                        shadowSize: [41, 41]
                    })
                }).addTo(map)
                .bindPopup(`
                    <div class="doctor-popup">
                        <strong>${doctor.name}</strong><br>
                        التخصص: ${doctor.specialty}<br>
                        العنوان: ${doctor.address}<br>
                        الهاتف: ${doctor.phone}<br>
                        ايام العمل: ${doctor.work_days}<br>
                        <button onclick="navigateToDoctor(${doctor.latitude}, ${doctor.longitude})">الوصول</button>
                        <button onclick="bookAppointment('${doctor.name}', '${doctor.specialty}')">حجز موعد</button>
                    </div>
                `);

                // إضافة معلومات الطبيب للعرض
                const doctorElement = document.createElement('div');
                doctorElement.classList.add('doctor-card');
                doctorElement.innerHTML = `
                    <h3>${doctor.name}</h3>
                    <p>التخصص: ${doctor.specialty}</p>
                    <p>العنوان: ${doctor.address}</p>
                    <button onclick="navigateToDoctor(${doctor.latitude}, ${doctor.longitude})">الوصول للطبيب</button>
                    <button onclick="bookAppointment('${doctor.name}', '${doctor.specialty}')">حجز موعد</button>
                `;
                doctorInfoContainer.appendChild(doctorElement);

                doctorMarkers.push(marker);
            });

            // التركيز على جميع العلامات
            if (doctorMarkers.length > 0) {
                const group = new L.featureGroup(doctorMarkers);
                map.fitBounds(group.getBounds().pad(0.1));
            }
        })
        .catch(error => {
            console.error('خطأ في جلب مواقع الأطباء:', error);
            alert('حدث خطأ في جلب مواقع الأطباء. يرجى المحاولة مرة أخرى.');
        });
}

    // دالة للتحقق من صحة الإحداثيات
    function isValidCoordinate(lat, lng) {
        // التحقق من نطاق إحداثيات الجزائر
        const isValidLat = lat >= 18 && lat <= 37;
        const isValidLng = lng >= -8 && lng <= 12;
        return isValidLat && isValidLng;
    }

    // دالة لتحميل مكتبة Leaflet
    function loadLeafletLibrary() {
        const leafletScript = document.createElement('script');
        leafletScript.src = 'https://unpkg.com/leaflet@1.7.1/dist/leaflet.js';
        leafletScript.onload = () => {
            const leafletCSS = document.createElement('link');
            leafletCSS.rel = 'stylesheet';
            leafletCSS.href = 'https://unpkg.com/leaflet@1.7.1/dist/leaflet.css';
            document.head.appendChild(leafletCSS);
            
            // تشغيل تهيئة الخريطة
            initializeMap();
        };
        document.head.appendChild(leafletScript);
    }

    // دالة لتحديد موقع المستخدم
    function getUserLocation() {
        return new Promise((resolve, reject) => {
            // التحقق من دعم المتصفح
            if (!navigator.geolocation) {
                reject(new Error('خدمة تحديد الموقع غير مدعومة في متصفحك'));
                return;
            }

            // خيارات متقدمة لتحديد الموقع
            const options = {
                enableHighAccuracy: true,  // تمكين الدقة العالية
                timeout: 10000,            // مهلة 10 ثوانٍ
                maximumAge: 0              // عدم استخدام الموقع المخزن مسبقًا
            };

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    userLocation = [position.coords.latitude, position.coords.longitude];
                    console.log('تم الحصول على موقع المستخدم');

                    const location = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                        timestamp: position.timestamp
                    };

                    // إرسال الموقع للخادم
                    fetch('/update_location', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(location)
                    });

                    resolve(location);
                },
                (error) => {
                    console.error('خطأ في تحديد الموقع:', error);
                    
                    // رسائل مفصلة حسب نوع الخطأ
                    switch(error.code) {
                        case error.PERMISSION_DENIED:
                            reject(new Error('تم رفض الوصول للموقع. يرجى السماح للتطبيق بالوصول للموقع.'));
                            break;
                        case error.POSITION_UNAVAILABLE:
                            reject(new Error('معلومات الموقع غير متوفرة. يرجى التحقق من إعدادات الموقع.'));
                            break;
                        case error.TIMEOUT:
                            reject(new Error('انتهت المهلة الزمنية للحصول على الموقع. يرجى المحاولة مرة أخرى.'));
                            break;
                        default:
                            reject(new Error('حدث خطأ غير معروف أثناء تحديد الموقع.'));
                    }
                },
                options
            );
        });
    }

    // دالة للبحث عن الأطباء
    function searchDoctors() {
        const searchInput = document.getElementById('doctorSearchInput');
        const searchTerm = searchInput.value.trim();

        // التحقق من صحة مدخلات البحث
        if (!searchTerm) {
            alert('الرجاء إدخال كلمة بحث');
            return;
        }

        // إرسال طلب البحث للخادم
        fetch('/search_doctors', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query: searchTerm })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('حدث خطأ أثناء البحث');
            }
            return response.json();
        })
        .then(doctors => {
            // مسح العلامات السابقة
            doctorMarkers.forEach(marker => map.removeLayer(marker));
            doctorMarkers = [];

            // إضافة علامات الأطباء الجدد
            doctors.forEach(doctor => {
                if (isValidCoordinate(doctor.latitude, doctor.longitude)) {
                    const marker = L.marker([doctor.latitude, doctor.longitude])
                        .addTo(map)
                        .bindPopup(`
                            <div class="doctor-popup">
                                <strong>${doctor.name}</strong><br>
                                <span>التخصص: ${doctor.specialty}</span><br>
                                <span>العنوان: ${doctor.address}</span><br>
                                <span>الهاتف: ${doctor.phone}</span><br>
                                <span>ايام العمل: ${doctor.work_days}</span><br>
                                <button onclick="navigateToDoctor(${doctor.latitude}, ${doctor.longitude})">الوصول</button>
                                <button onclick="bookAppointment('${doctor.name}', '${doctor.specialty}')">حجز موعد</button>
                            </div>
                        `);
                    doctorMarkers.push(marker);
                }
            });

            // التركيز على المنطقة التي بها الأطباء
            if (doctorMarkers.length > 0) {
                const group = new L.featureGroup(doctorMarkers);
                map.fitBounds(group.getBounds());
                
                // عرض عدد النتائج
                alert(`تم العثور على ${doctors.length} طبيب`);
            } else {
                alert('لم يتم العثور على أطباء');
            }
        })
        .catch(error => {
            console.error('خطأ في البحث عن الأطباء:', error);
            alert('حدث خطأ أثناء البحث');
        });
    }

    // إضافة مستمع الحدث لزر البحث
    const doctorSearchButton = document.getElementById('doctorSearchButton');
    doctorSearchButton.addEventListener('click', searchDoctors);

    // دعم البحث عند الضغط على Enter
    const doctorSearchInput = document.getElementById('doctorSearchInput');
    doctorSearchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            searchDoctors();
        }
    });

    // إضافة مستمعي الأحداث
    sendButton.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        // إرسال الرسالة عند الضغط على Enter
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // معالج حدث زر المعلومات
    infoIcon.addEventListener('click', () => {
        alert('الشفاء+ : نسخة تجريبية\n مصمم للمساعدة في الاستشارات الطبية');
    });

    // معالج حدث تبديل الصوت
    voiceToggle.addEventListener('click', () => {
        // تبديل حالة الصوت
        isSoundEnabled = !isSoundEnabled;
        voiceToggle.innerHTML = isSoundEnabled 
            ? '<i class="fas fa-volume-up" title="إيقاف الصوت"></i>' 
            : '<i class="fas fa-volume-mute" title="تشغيل الصوت"></i>';
    });

    // إنشاء زر التبرعات
    const donationIcon = document.createElement('div');
    donationIcon.innerHTML = '<i class="fas fa-hand-holding-heart" title="التبرعات"></i>';
    donationIcon.classList.add('donation-icon');
    donationIcon.addEventListener('click', showDonationModal);
    document.querySelector('.header-icons').appendChild(donationIcon);

    // دالة عرض نافذة التبرعات
    function showDonationModal() {
        // إنشاء النافذة المنبثقة للتبرعات
        const donationModal = document.createElement('div');
        donationModal.classList.add('donation-modal');
        donationModal.innerHTML = `
            <div class="donation-modal-content">
                <span class="close-donation-modal">&times;</span>
                <h2>التبرعات الطبية</h2>
                <div class="donation-options">
                    <div class="donation-option">
                        <i class="fas fa-pills"></i>
                        <h3>التبرع بالأدوية</h3>
                        <p>ساهم في توفير الأدوية للمحتاجين</p>
                        <button onclick="donateType('medications')">تبرع بالأدوية</button>
                    </div>
                    <div class="donation-option">
                        <i class="fas fa-stethoscope"></i>
                        <h3>المعدات الطبية</h3>
                        <p>تبرع بالمعدات الطبية لدعم المراكز الصحية</p>
                        <button onclick="donateType('medical_equipment')">تبرع بالمعدات</button>
                    </div>
                    <div class="donation-option">
                        <i class="fas fa-donate"></i>
                        <h3>التبرع المالي</h3>
                        <p>ادعم برامج الرعاية الصحية</p>
                        <button onclick="donateType('monetary')">تبرع مالي</button>
                    </div>
                </div>
            </div>
        `;

        // إضافة النافذة إلى الصفحة
        document.body.appendChild(donationModal);

        // إغلاق النافذة
        const closeModal = donationModal.querySelector('.close-donation-modal');
        closeModal.addEventListener('click', () => {
            document.body.removeChild(donationModal);
        });
    }

    // دالة معالجة نوع التبرع
    function donateType(type) {
        switch(type) {
            case 'medications':
                alert('شكرًا لرغبتك في التبرع بالأدوية. سيتم التواصل معك قريبًا.');
                break;
            case 'medical_equipment':
                alert('شكرًا لرغبتك في التبرع بالمعدات الطبية. سيتم التواصل معك قريبًا.');
                break;
            case 'monetary':
                alert('شكرًا لرغبتك في التبرع المالي. سيتم توجيهك إلى وسائل الدفع.');
                break;
        }
    }

    // تحميل مكتبة Leaflet
    loadLeafletLibrary();

    // تحديد موقع المستخدم
    getUserLocation();

    // رسالة ترحيبية أولية
    addMessage('مرحبًا! أنا مساعدك الطبي الذكي. كيف يمكنني مساعدتك اليوم؟', 'bot');

    // إيقاف الصوت تلقائياً عند مغادرة الصفحة
    window.addEventListener('beforeunload', () => {
        fetch('/stop_audio', {
            method: 'POST'
        });
    });

    // دالة حجز موعد مع الطبيب
    window.bookAppointment = function(doctorName, specialty) {
        // فتح نافذة منبثقة لحجز الموعد
        const appointmentModal = document.createElement('div');
        appointmentModal.classList.add('appointment-modal');
        appointmentModal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>حجز موعد مع ${doctorName}</h2>
                    <button onclick="closeAppointmentModal()" class="close-btn">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="specialty">التخصص: ${specialty}</p>
                    <form id="appointmentForm">
                        <div class="form-group">
                            <label for="appointmentDate">اختر التاريخ:</label>
                            <input type="date" id="appointmentDate" required min="${new Date().toISOString().split('T')[0]}">
                        </div>
                        <div class="form-group">
                            <label for="appointmentTime">اختر الوقت:</label>
                            <input type="time" id="appointmentTime" >
                        </div>
                        <div class="form-group">
                            <label for="patientName">اسم المريض:</label>
                            <input type="text" id="patientName" required placeholder="أدخل اسمك الكامل">
                        </div>
                        <div class="form-group">
                            <label for="patientPhone">رقم الهاتف:</label>
                            <input type="tel" id="patientPhone" required pattern="[0-9]{10}" placeholder="مثال: 0612345678">
                        </div>
                        <div class="form-group">
                            <label for="appointmentReason">سبب الزيارة:</label>
                            <textarea id="appointmentReason" placeholder="وصف مختصر للحالة (اختياري)"></textarea>
                        </div>
                        <button type="submit" class="submit-btn">تأكيد الحجز</button>
                    </form>
                </div>
            </div>
        `;
        document.body.appendChild(appointmentModal);

        // معالجة إرسال نموذج الحجز
        document.getElementById('appointmentForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            // جمع بيانات النموذج
            const date = document.getElementById('appointmentDate').value;
            const time = document.getElementById('appointmentTime').value;
            const patientName = document.getElementById('patientName').value;
            const patientPhone = document.getElementById('patientPhone').value;
            const appointmentReason = document.getElementById('appointmentReason').value || 'لا يوجد';

            // التحقق من صحة رقم الهاتف
            const phoneRegex = /^0[5-7][0-9]{8}$/;
            if (!phoneRegex.test(patientPhone)) {
                alert('يرجى إدخال رقم هاتف جزائري صحيح (10 أرقام يبدأ بـ 05، 06، 07)');
                return;
            }

            // إرسال طلب حجز الموعد إلى الخادم
            fetch('/book-appointment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    doctorName: doctorName,
                    specialty: specialty,
                    date: date,
                    time: time,
                    patientName: patientName,
                    patientPhone: patientPhone,
                    appointmentReason: appointmentReason
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    // إنشاء رسالة تأكيد مفصلة
                    const confirmationMessage = `
                        تم حجز الموعد بنجاح 
                        
                        الطبيب: ${doctorName}
                        التخصص: ${specialty}
                        التاريخ: ${date}
                        الوقت: ${time}
                        
                        سيتم التواصل معك قريبًا لتأكيد الموعد`;
                    
                    alert(confirmationMessage);
                    closeAppointmentModal();
                } else {
                    alert(data.message || 'فشل حجز الموعد. يرجى المحاولة مرة أخرى.');
                }
            })
            .catch(error => {
                console.error('خطأ:', error);
                alert('حدث خطأ أثناء حجز الموعد. تأكد من اتصالك بالإنترنت.');
            });
        });
    }

    // دالة إغلاق نافذة الحجز
    window.closeAppointmentModal = function() {
        const appointmentModal = document.querySelector('.appointment-modal');
        if (appointmentModal) {
            appointmentModal.remove();
        }
    }

    // إضافة أنماط CSS لتنسيق الرسائل
    const messageStyles = document.createElement('style');
    messageStyles.textContent = `
        .message-content strong, 
        .message-content u, 
        .message-content code {
            margin: 0 2px;
            line-height: 1.4;
        }
        
        .message-content br {
            line-height: 0.8;
            margin: 2px 0;
        }
        
        .message-content h1, .message-content h2, .message-content h3, .message-content h4, .message-content h5, .message-content h6 {
            margin-top: 0.5em;
            margin-bottom: 0.5em;
        }
    `;
    document.head.appendChild(messageStyles);

    const ChatEnhancer = {
        // تحسين إدخال المستخدم
        enhanceUserInput() {
            userInput.addEventListener('keydown', (event) => {
                // اختصار Ctrl+Enter للإرسال
                if (event.ctrlKey && event.key === 'Enter') {
                    sendMessage();
                }
            });
        },

        visualEffects: {
            messageTransitions() {
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            entry.target.classList.add('visible');
                        }
                    });
                }, { threshold: 0.1 });

                document.querySelectorAll('.message').forEach(msg => {
                    msg.classList.add('fade-in');
                    observer.observe(msg);
                });
            },

            typingIndicator() {
                const typingIndicator = document.createElement('div');
                typingIndicator.classList.add('typing-indicator');
                typingIndicator.innerHTML = `
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                `;
                chatMessages.appendChild(typingIndicator);
                return typingIndicator;
            }
        },

        // تهيئة التحسينات
        init() {
            this.enhanceUserInput();
            this.visualEffects.messageTransitions();
        }
    };

    // تعديل دالة إرسال الرسالة
    async function sendMessage() {
        const message = userInput.value.trim();
        
        // الإجراء الأساسي للرسالة
        if (message === '') return;

        addMessage(message, 'user');
        userInput.value = '';

        try {
            // عرض مؤشر الكتابة
            const typingIndicator = ChatEnhancer.visualEffects.typingIndicator();
            
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message: message })
            });

            // إزالة مؤشر الكتابة
            typingIndicator.remove();

            const data = await response.json();
            addMessage(data.response, 'bot');
        } catch (error) {
            console.error('Error:', error);
            addMessage('حدث خطأ أثناء إرسال الرسالة', 'bot');
        }
    }

    // إضافة أنماط CSS للتحسينات
    const enhancementStyles = document.createElement('style');
    enhancementStyles.textContent = `
        .message {
            opacity: 0;
            transform: translateY(20px);
            transition: opacity 0.5s, transform 0.5s;
        }
        .message.visible {
            opacity: 1;
            transform: translateY(0);
        }
        .typing-indicator {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 10px;
        }
        .typing-dot {
            width: 8px;
            height: 8px;
            background-color: #888;
            border-radius: 50%;
            margin: 0 4px;
            animation: typing 1.4s infinite;
        }
        @keyframes typing {
            0%, 100% { opacity: 0.4; }
            50% { opacity: 1; }
        }
    `;
    document.head.appendChild(enhancementStyles);

    // تشغيل المحسنات
    ChatEnhancer.init();
});
