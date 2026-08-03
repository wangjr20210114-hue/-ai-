package com.floris.android.ui.auth

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.core.auth.AuthManager
import com.floris.android.ui.components.AuroraOrb
import com.floris.android.ui.components.pressable
import com.floris.android.ui.loginViewModelFactory
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class LoginViewModel(private val authManager: AuthManager) : ViewModel() {

    data class UiState(
        val email: String = "",
        val code: String = "",
        val step: Step = Step.EMAIL,
        val busy: Boolean = false,
        val error: String? = null,
    )

    enum class Step { EMAIL, CODE }

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    fun updateEmail(value: String) { _state.value = _state.value.copy(email = value, error = null) }
    fun updateCode(value: String) { _state.value = _state.value.copy(code = value.filter { it.isDigit() }.take(6), error = null) }

    fun sendCode() {
        val email = _state.value.email.trim()
        if (busy() || !email.contains("@")) {
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
        if (busy() || current.code.length < 4) {
            _state.value = current.copy(error = "请输入邮箱收到的验证码")
            return
        }
        _state.value = current.copy(busy = true, error = null)
        viewModelScope.launch {
            runCatching { authManager.verifyEmailOtp(current.email, current.code) }
                .onFailure { _state.value = _state.value.copy(busy = false, error = it.message) }
            // Success flips AuthState → the nav host replaces this screen.
        }
    }

    fun back() { _state.value = _state.value.copy(step = Step.EMAIL, code = "", error = null) }

    private fun busy() = _state.value.busy
}

@Composable
fun LoginScreen(container: AppContainer) {
    val viewModel: LoginViewModel = viewModel(factory = container.loginViewModelFactory())
    val state by viewModel.state.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .systemBarsPadding()
            .imePadding()
            .padding(horizontal = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        AuroraOrb(size = 84.dp)
        Spacer(Modifier.height(24.dp))
        Text("Floris", style = MaterialTheme.typography.displayMedium)
        Spacer(Modifier.height(8.dp))
        Text(
            "你的 AI 工作伙伴",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(40.dp))

        AnimatedContent(
            targetState = state.step,
            transitionSpec = {
                (slideInHorizontally { it / 3 } + fadeIn()) togetherWith
                    (slideOutHorizontally { -it / 3 } + fadeOut())
            },
            label = "loginStep",
        ) { step ->
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                when (step) {
                    LoginViewModel.Step.EMAIL -> {
                        OutlinedTextField(
                            value = state.email,
                            onValueChange = viewModel::updateEmail,
                            label = { Text("邮箱") },
                            placeholder = { Text("you@example.com") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                            singleLine = true,
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Spacer(Modifier.height(16.dp))
                        Button(
                            onClick = viewModel::sendCode,
                            enabled = !state.busy,
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth().height(50.dp),
                        ) { Text(if (state.busy) "发送中…" else "发送验证码") }
                    }
                    LoginViewModel.Step.CODE -> {
                        Text(
                            "验证码已发送至\n${state.email}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            textAlign = TextAlign.Center,
                        )
                        Spacer(Modifier.height(16.dp))
                        OutlinedTextField(
                            value = state.code,
                            onValueChange = viewModel::updateCode,
                            label = { Text("验证码") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                            singleLine = true,
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Spacer(Modifier.height(16.dp))
                        Button(
                            onClick = viewModel::verify,
                            enabled = !state.busy,
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth().height(50.dp),
                        ) { Text(if (state.busy) "登录中…" else "登录") }
                        Spacer(Modifier.height(8.dp))
                        TextButton(onClick = viewModel::back) { Text("返回修改邮箱") }
                    }
                }
            }
        }

        state.error?.let {
            Spacer(Modifier.height(12.dp))
            Text(it, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.error)
        }
    }
}
