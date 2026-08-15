package com.hyperscale.command.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hyperscale.command.core.model.Capability
import com.hyperscale.command.core.model.CapabilityType
import com.hyperscale.command.core.model.CapabilityValue
import com.hyperscale.command.ui.theme.LocalStatusColours
import kotlin.math.roundToInt

/**
 * Renders one Homey capability with the right control for its type.
 *
 * Read-only capabilities (sensor readings) render as a value, never as a disabled control — a
 * greyed-out slider on a temperature sensor implies the user did something wrong.
 */
@Composable
fun CapabilityControl(
    capability: Capability,
    enabled: Boolean,
    onSetBoolean: (Boolean) -> Unit,
    onSetNumber: (Double) -> Unit,
    onSetString: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when {
                capability.type == CapabilityType.BOOLEAN && capability.settable ->
                    BooleanControl(capability, enabled, onSetBoolean)

                capability.type == CapabilityType.NUMBER && capability.settable ->
                    NumberControl(capability, enabled, onSetNumber)

                capability.type == CapabilityType.ENUM && capability.settable ->
                    EnumControl(capability, enabled, onSetString)

                else -> ReadOnlyControl(capability)
            }
        }
    }
}

@Composable
private fun BooleanControl(
    capability: Capability,
    enabled: Boolean,
    onSet: (Boolean) -> Unit,
) {
    val statusColours = LocalStatusColours.current
    val checked = (capability.value as? CapabilityValue.Bool)?.value == true

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = capability.title,
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.weight(1f),
        )
        Switch(
            checked = checked,
            onCheckedChange = onSet,
            enabled = enabled,
            colors = SwitchDefaults.colors(checkedTrackColor = statusColours.controllable),
        )
    }
}

@Composable
private fun NumberControl(
    capability: Capability,
    enabled: Boolean,
    onSet: (Double) -> Unit,
) {
    val min = (capability.min ?: 0.0).toFloat()
    val max = (capability.max ?: 1.0).toFloat().let { if (it <= min) min + 1f else it }
    val current = (capability.value as? CapabilityValue.Num)?.value?.toFloat() ?: min

    // Local state keeps the thumb under the finger; the committed value goes out on release,
    // so a drag does not fire dozens of HTTP writes at the hub.
    var draft by remember(capability.id, current) { mutableFloatStateOf(current.coerceIn(min, max)) }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(text = capability.title, style = MaterialTheme.typography.titleMedium)
        Text(
            text = formatValue(draft.toDouble(), capability),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary,
        )
    }

    Slider(
        value = draft,
        onValueChange = { draft = it },
        onValueChangeFinished = { onSet(draft.toDouble()) },
        valueRange = min..max,
        steps = capability.step
            ?.takeIf { it > 0 }
            ?.let { step -> (((max - min) / step).toInt() - 1).coerceIn(0, 100) }
            ?: 0,
        enabled = enabled,
    )
}

@Composable
private fun EnumControl(
    capability: Capability,
    enabled: Boolean,
    onSet: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val current = (capability.value as? CapabilityValue.Text)?.value

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = capability.title,
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.weight(1f),
        )

        Column {
            OutlinedButton(onClick = { expanded = true }, enabled = enabled) {
                Text(
                    text = current ?: "Choose",
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                capability.options.forEach { option ->
                    DropdownMenuItem(
                        text = { Text(option) },
                        onClick = {
                            expanded = false
                            onSet(option)
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun ReadOnlyControl(capability: Capability) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = capability.title,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = displayValue(capability),
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurface,
        )
    }
}

private fun displayValue(capability: Capability): String = when (val value = capability.value) {
    is CapabilityValue.Bool -> if (value.value) "Yes" else "No"
    is CapabilityValue.Num -> formatValue(value.value, capability)
    is CapabilityValue.Text -> value.value
    CapabilityValue.Absent -> "—"
}

private fun formatValue(value: Double, capability: Capability): String {
    val rounded = if (value % 1.0 == 0.0) {
        value.roundToInt().toString()
    } else {
        String.format(java.util.Locale.getDefault(), "%.1f", value)
    }
    return capability.unit?.let { "$rounded $it" } ?: rounded
}
