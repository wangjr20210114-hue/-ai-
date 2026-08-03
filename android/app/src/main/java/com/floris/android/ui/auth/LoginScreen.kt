package com.floris.android.ui.auth

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.ContentTransform
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.auth.AuthManager
import com.floris.android.core.auth.AuthState
import com.floris.android.ui.components.CatAvatar
import com.floris.android.ui.components.PillButton
import com.floris.android.ui.components.PillStyle
import com.floris.android.ui.layout.Responsive
import com.floris.android.ui.loginViewModelFactory
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class LoginViewModel(private val authManager: AuthManager) : ViewModel() {

    data class UiState(
        val email: String = "",
        val code: String = "",
        val step: Step = Step.EMAIL,
        /**邮箱流程忙碌（发送验证码 / 校验），只影响上方按钮。 */
        val busy: Boolean = false,
        /** 游客登录忙碌，与邮箱流程分开，否则会误改上方按钮文案。 */
        val guestBusy: Boolean = false,
        val error: String? = null,
    ) {
        /** 任一流程进行中：用于禁用另一侧按钮，避免并发登录。 */
        val anyBusy: Boolean get() = busy || guestBusy
    }

    enum class Step { EMAIL, CODE }

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    init {
        // 退出登录后本页可能被复用（导航层只是把它换回来），
        // 必须清掉上一次的验证码步骤，否则会停在"修改邮箱"那一屏。
        viewModelScope.launch {
            authManager.state.collect { auth ->
                if (auth is AuthState.SignedOut) reset()
            }
        }
    }

    /** 回到初始的邮箱输入态，清空所有残留。 */
    fun reset() {
        _state.value = UiState()
    }

    fun updateEmail(value: String) {
        _state.value = _state.value.copy(email = value, error = null)
    }

    fun updateCode(value: String) {
        _state.value = _state.value.copy(
            code = value.filter { it.isDigit() }.take(6),
            error = null,
        )
    }

    fun sendCode() {
        val email = _state.value.email.trim()
        if (_state.value.anyBusy) return
        if (!email.contains("@")) {
            _state.value = _state.value.copy(error = "请输入有效的邮箱地址")
            return
        }
        _state.value = _state.value.copy(busy = true, error = null)
        viewModelScope.launch {
            runCatching { authManager.sendEmailOtp(email) }
                .onSuccess { _state.value = _state.value.copy(busy = false, step = Step.CODE) }
                .onFailure { _state.value = _state.value.copy(busy = false, error = it.message) }
        }
    }

    fun verify() {
        val current = _state.value
        if (current.anyBusy) return
        if (current.code.length < 4) {
            _state.value = current.copy(error = "请输入邮箱收到的验证码")
            return
        }
        _state.value = current.copy(busy = true, error = null)
        viewModelScope.launch {
            runCatching { authManager.verifyEmailOtp(current.email, current.code) }
                .onFailure { _state.value = _state.value.copy(busy = false, error = it.message) }
            // 成功后 AuthState 翻转，导航层会替换本页
        }
    }

    fun back() {
        _state.value = _state.value.copy(step = Step.EMAIL, code = "", error = null)
    }

    /**
     * 游客登录：向后端领取一枚游客会话（GET /auth/session）。
     * 成功后 AuthState 翻转，导航层会替换本页。
     */
    fun continueAsGuest() {
        if (_state.value.anyBusy) return
        // 用独立的 guestBusy：共用 busy 会让上方按钮变成"发送中…"，
        // 看起来就像点游客入口同时触发了发送验证码。
        _state.value = _state.value.copy(guestBusy = true, error = null)
        viewModelScope.launch {
            runCatching { authManager.signInAsGuest() }
                .onFailure {
                    _state.value = _state.value.copy(guestBusy = false, error = it.message)
                }
        }
    }
}

@Composable
fun LoginScreen(container: AppContainer) {
    val viewModel: LoginViewModel = viewModel(factory = container.loginViewModelFactory())
    val state by viewModel.state.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .systemBarsPadding()
            .imePadding()
            // 可滚动：键盘弹出时内容不会溢出屏幕，避免按钮被挤到重叠区域。
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Responsive.horizontalPadding + 14.dp, vertical = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        // 横屏可用高度只有竖屏四成，头像与间距同步收小，避免按钮被挤出屏幕。
        CatAvatar(size = Responsive.loginAvatar)
        Spacer(Modifier.height(Responsive.gap(18.dp)))
        Text("FLORIS", style = MaterialTheme.typography.displayMedium)
        Spacer(Modifier.height(6.dp))
        Text(
            t(StringKey.AppTagline),
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.primary,
        )
        Spacer(Modifier.height(Responsive.gap(42.dp)))

        AnimatedContent(
            targetState = state.step,
            transitionSpec = {
                ContentTransform(
                    targetContentEnter = slideInHorizontally { it / 3 } + fadeIn(),
                    initialContentExit = slideOutHorizontally { -it / 3 } + fadeOut(),
                    // 关键：退场内容不再参与布局尺寸，否则旧的"发送验证码"按钮
                    // 仍会占位并抢走点击，导致点游客入口同时触发发送验证码。
                    sizeTransform = SizeTransform(clip = false) { _, target ->
                        tween(220)
                    },
                )
            },
            label = "loginStep",
        ) { step ->
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                when (step) {
                    LoginViewModel.Step.EMAIL -> {
                        SoftField(
                            value = state.email,
                            onValueChange = viewModel::updateEmail,
                            hint = "you@example.com",
                            keyboardType = KeyboardType.Email,
                        )
                        Spacer(Modifier.height(14.dp))
                        PillButton(
                            text = if (state.busy) t(StringKey.LoginSending)
                            else t(StringKey.LoginSendCode),
                            onClick = viewModel::sendCode,
                            enabled = !state.anyBusy,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }

                    LoginViewModel.Step.CODE -> {
                        Text(
                            "${t(StringKey.LoginCodeSentTo)}\n${state.email}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            textAlign = TextAlign.Center,
                        )
                        Spacer(Modifier.height(16.dp))
                        SoftField(
                            value = state.code,
                            onValueChange = viewModel::updateCode,
                            hint = t(StringKey.LoginCode),
                            keyboardType = KeyboardType.NumberPassword,
                            center = true,
                        )
                        Spacer(Modifier.height(14.dp))
                        PillButton(
                            text = if (state.busy) t(StringKey.LoginSigningIn)
                            else t(StringKey.LoginSignIn),
                            onClick = viewModel::verify,
                            enabled = !state.anyBusy,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Spacer(Modifier.height(4.dp))
                        PillButton(
                            text = t(StringKey.LoginBackToEmail),
                            onClick = viewModel::back,
                            style = PillStyle.Ghost,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }
        }

        state.error?.let {
            Spacer(Modifier.height(14.dp))
            Text(
                it,
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.error,
                textAlign = TextAlign.Center,
            )
        }

        // 游客入口：后端签发 7 天游客会话，不需要邮箱即可先体验。
        Spacer(Modifier.height(Responsive.gap(26.dp)))
        Row(verticalAlignment = Alignment.CenterVertically) {
            HairLine(Modifier.weight(1f))
            Text(
                t(StringKey.LoginOr),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                modifier = Modifier.padding(horizontal = 10.dp),
            )
            HairLine(Modifier.weight(1f))
        }
        Spacer(Modifier.height(Responsive.gap(14.dp)))
        PillButton(
            text = if (state.guestBusy) t(StringKey.LoginSigningIn)
            else t(StringKey.LoginAsGuest),
            onClick = viewModel::continueAsGuest,
            style = PillStyle.Tonal,
            enabled = !state.anyBusy,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Text(
            t(StringKey.GuestUpgradeHint),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f),
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun HairLine(modifier: Modifier = Modifier) {
    Box(
        modifier
            .height(1.dp)
            .background(MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.14f)),
    )
}

/** 柔和输入框：无描边、药丸底衬，避免突兀的传统文本框。 */
@Composable
private fun SoftField(
    value: String,
    onValueChange: (String) -> Unit,
    hint: String,
    keyboardType: KeyboardType,
    center: Boolean = false,
) {
    Box(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(999.dp))
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 20.dp, vertical = 15.dp),
        contentAlignment = if (center) Alignment.Center else Alignment.CenterStart,
    ) {
        if (value.isEmpty()) {
            Text(
                hint,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = true,
            textStyle = MaterialTheme.typography.bodySmall.copy(
                color = MaterialTheme.colorScheme.onSurface,
                textAlign = if (center) TextAlign.Center else TextAlign.Start,
            ),
            cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
            keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
