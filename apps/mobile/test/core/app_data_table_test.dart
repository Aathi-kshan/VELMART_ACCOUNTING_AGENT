import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/app_data_table.dart';

void main() {
  testWidgets('table min width follows the parent pane, not the window', (tester) async {
    tester.view.physicalSize = const Size(1400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 400,
            child: AppDataTable(
              columns: [
                DataColumn(label: Text('A')),
                DataColumn(label: Text('B')),
              ],
              rows: [
                DataRow(cells: [DataCell(Text('1')), DataCell(Text('2'))]),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final table = tester.getSize(find.byType(DataTable));
    expect(table.width, lessThan(500));
  });
}
