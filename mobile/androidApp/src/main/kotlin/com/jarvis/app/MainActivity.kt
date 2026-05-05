package com.jarvis.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.jarvis.shared.audio.AudioPlayer
import com.jarvis.shared.audio.AudioRecorder
import com.jarvis.shared.net.JarvisClient
import com.jarvis.shared.net.JarvisWebSocket
import com.jarvis.shared.ui.AssistantPhase
import com.jarvis.shared.ui.AssistantViewModel

class MainActivity : ComponentActivity() {
    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* user response handled implicitly; recorder will fail gracefully if denied */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            micPermission.launch(Manifest.permission.RECORD_AUDIO)
        }

        val client = JarvisClient(BuildConfig.BASE_URL, BuildConfig.API_KEY)
        val ws = JarvisWebSocket(BuildConfig.BASE_URL, BuildConfig.API_KEY)
        val vm = AssistantViewModel(
            client = client,
            ws = ws,
            recorder = AudioRecorder(),
            player = AudioPlayer(),
            sessionId = "android-${System.currentTimeMillis()}",
        )

        setContent {
            MaterialTheme { Surface(Modifier.fillMaxSize()) { AssistantScreen(vm) } }
        }
    }
}

@Composable
private fun AssistantScreen(vm: AssistantViewModel) {
    val state by vm.state.collectAsState()
    var input by remember { mutableStateOf("") }

    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Jarvis", style = MaterialTheme.typography.headlineMedium)
        Text("State: ${state.phase}")

        OutlinedTextField(
            value = input,
            onValueChange = { input = it },
            label = { Text("Type a command") },
            modifier = Modifier.fillMaxSize().height(64.dp),
        )
        Button(onClick = {
            if (input.isNotBlank()) { vm.sendText(input); input = "" }
        }) { Text("Send") }

        Spacer(Modifier.height(8.dp))

        Button(
            onClick = {
                if (state.phase == AssistantPhase.Listening) vm.stopVoiceTurn()
                else vm.startVoiceTurn()
            }
        ) {
            Text(if (state.phase == AssistantPhase.Listening) "Stop" else "Hold to speak")
        }

        if (state.transcript.isNotEmpty()) Text("You: ${state.transcript}")
        if (state.reply.isNotEmpty()) Text("Jarvis: ${state.reply}")
        state.error?.let { Text("Error: $it", color = MaterialTheme.colorScheme.error) }
    }
}
