-keepattributes Signature, *Annotation*, InnerClasses, EnclosingMethod
-dontwarn okhttp3.**
-dontwarn okio.**
-keepclassmembers class * {
    @kotlinx.serialization.Serializable <fields>;
}
-keepclasseswithmembers class * {
    @kotlinx.serialization.Serializable <init>(...);
}
-keep,includedescriptorclasses class com.floris.android.**$$serializer { *; }
-keepclassmembers class com.floris.android.** {
    *** Companion;
}
-keepclasseswithmembers class com.floris.android.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-if @kotlinx.serialization.Serializable class **
-keep class <1> { *; }
