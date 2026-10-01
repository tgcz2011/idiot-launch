import 'package:flutter_test/flutter_test.dart';
import 'package:idiot_launch/main.dart';

void main() {
  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const IdiotLaunchApp());
    expect(find.text('傻瓜启动器'), findsOneWidget);
  });
}
