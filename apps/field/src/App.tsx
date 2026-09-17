import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, View } from 'react-native';

export default function App() {
  return (
    <View style={styles.container}>
      <Text style={styles.heading}>Field Inspection</Text>
      <Text style={styles.body}>
        Scaffold. Walk download and capture land with the field app change.
      </Text>
      <StatusBar style="auto" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  heading: { fontSize: 22, fontWeight: '600', marginBottom: 8 },
  body: { fontSize: 16, textAlign: 'center' },
});
